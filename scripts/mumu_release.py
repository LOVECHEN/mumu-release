#!/usr/bin/env python3
"""MuMu 官方安装包镜像、Release 合并与排序工具。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


USER_AGENT = "Mozilla/5.0"
SPLIT_MAX = 1_992_294_400  # 1900 MiB，低于 GitHub Release 单文件 2 GiB 上限。
CHECKSUM_NAME = "checksums.sha256"

class ToolError(RuntimeError):
    """可安全显示给 Actions 日志的工具错误。"""


def log(message: str) -> None:
    print(message, flush=True)


def run_command(
    args: Sequence[str],
    *,
    input_text: str | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env) if env is not None else None,
        check=False,
    )
    if check and result.returncode != 0:
        # 第三方命令可能把 URL、认证头或请求正文写入 stderr，失败日志只保留命令名和退出码。
        raise ToolError(f"命令失败({result.returncode}): {args[0]}")
    return result


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ToolError(f"缺少环境变量 {name}")
    return value


def mask_source_hosts(values: Iterable[str]) -> None:
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for value in values:
        if not value:
            continue
        parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
        host = parsed.hostname or value.split("/", 1)[0]
        if host:
            log(f"::add-mask::{host}")


def extract_version(value: str) -> str:
    match = re.search(r"\d+\.\d+\.\d+", value)
    return match.group(0) if match else ""


def version_key(value: str) -> tuple[int, ...]:
    version = extract_version(value)
    return tuple(int(part) for part in version.split(".")) if version else (0,)


def filename_from_url(url: str) -> str:
    return Path(urllib.parse.urlsplit(url).path).name


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", raw_line)
        if match:
            checksums[match.group(2)] = match.group(1).lower()
    return checksums


def format_checksums(checksums: Mapping[str, str]) -> str:
    return "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums))


def split_suffix(index: int) -> str:
    if not 0 <= index < 26 * 26:
        raise ToolError("分卷数量超过 676")
    return chr(ord("a") + index // 26) + chr(ord("a") + index % 26)


def split_file(path: Path, limit: int = SPLIT_MAX) -> tuple[list[Path], str]:
    original_hash = sha256_file(path)
    parts: list[Path] = []
    with path.open("rb") as source:
        index = 0
        while True:
            chunk = source.read(limit)
            if not chunk:
                break
            part = path.with_name(f"{path.name}.part.{split_suffix(index)}")
            part.write_bytes(chunk)
            parts.append(part)
            index += 1
    path.unlink()
    return parts, original_hash


def asset_kind(name: str) -> str:
    classifier = private_plugin().get("asset_kind")
    if not callable(classifier):
        raise ToolError("私有同步扩展缺少 asset_kind")
    result = classifier(name)
    return str(result) if result else "安装包"


def build_release_notes(
    assets: Sequence[Mapping[str, Any]],
    checksum_text: str,
    split_info: Mapping[str, tuple[str, int]] | None = None,
) -> str:
    lines = ["### 下载文件", "", "| 类型 | 文件 | 大小 |", "|------|------|------|"]
    for asset in sorted(assets, key=lambda item: str(item["name"])):
        name = str(asset["name"])
        if name == CHECKSUM_NAME:
            continue
        size = int(asset.get("size") or 0)
        lines.append(f"| {asset_kind(name)} | `{name}` | {size // 1_048_576} MB |")
    lines.extend(("", "### SHA256 校验", "```", checksum_text.rstrip(), "```"))
    if split_info:
        lines.extend(
            (
                "",
                "### 📦 分卷合并(该文件超 2 GiB 已切片,下齐全部 `.part.*` 再合并)",
                "",
            )
        )
    for original, (digest, count) in sorted((split_info or {}).items()):
        lines.extend(
            (
                f"**`{original}`**(共 {count} 卷:`{original}.part.aa` … )",
                f'- Windows(cmd):`copy /b "{original}.part.*" "{original}"`',
                f'- macOS / Linux:`cat "{original}".part.* > "{original}"`',
                f"- 合并后整包 SHA256(核对):`{digest}`",
                "",
            )
        )
    return "\n".join(lines) + "\n"


class HttpClient:
    def __init__(self) -> None:
        self.context = ssl.create_default_context()

    def _open(self, request: urllib.request.Request, timeout: int):
        return urllib.request.urlopen(request, timeout=timeout, context=self.context)

    def head(self, url: str, timeout: int = 25) -> Mapping[str, str] | None:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        try:
            with self._open(request, timeout) as response:
                return dict(response.headers.items())
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            return None

    def exists(self, url: str) -> bool:
        return self.head(url) is not None

    def redirect_target(self, url: str, timeout: int = 40) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._open(request, timeout) as response:
                return response.geturl()
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            return ""

    def get_text(self, url: str, timeout: int = 40) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with self._open(request, timeout) as response:
            return response.read().decode("utf-8", "replace")

    def download(self, url: str, destination: Path, attempts: int = 5) -> None:
        temporary = destination.with_name(f".{destination.name}.download")
        for attempt in range(1, attempts + 1):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with self._open(request, 40) as response, temporary.open("wb") as output:
                    expected = int(response.headers.get("Content-Length") or 0)
                    copied = 0
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        copied += len(chunk)
                if expected and copied != expected:
                    raise ToolError(f"下载长度不符:期望 {expected},实际 {copied}")
                temporary.replace(destination)
                return
            except (OSError, ToolError, urllib.error.URLError, urllib.error.HTTPError) as error:
                temporary.unlink(missing_ok=True)
                if attempt == attempts:
                    raise ToolError(f"下载失败({type(error).__name__}): {destination.name}") from error
                time.sleep(6)

    def post_form_json(
        self,
        url: str,
        fields: Mapping[str, str],
        headers: Mapping[str, str],
        timeout: int = 25,
    ) -> Mapping[str, Any]:
        body = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(url, data=body, method="POST")
        for key, value in headers.items():
            request.add_header(key, value)
        with self._open(request, timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))


class GitHub:
    def __init__(self, repo: str) -> None:
        self.repo = repo

    def gh(self, *args: str, input_text: str | None = None, check: bool = True) -> str:
        result = run_command(("gh", *args), input_text=input_text, check=check)
        return result.stdout

    def api_json(
        self,
        endpoint: str,
        *,
        method: str | None = None,
        payload: Mapping[str, Any] | None = None,
        check: bool = True,
    ) -> Any:
        args = ["api"]
        if method:
            args.extend(("--method", method))
        if payload is not None:
            args.extend(("--input", "-"))
        args.append(endpoint)
        output = self.gh(*args, input_text=json.dumps(payload) if payload is not None else None, check=check)
        return json.loads(output) if output.strip() else None

    def list_releases(self) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self.api_json(f"repos/{self.repo}/releases?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ToolError("GitHub Releases 响应格式错误")
            releases.extend(batch)
            if len(batch) < 100:
                return releases
            page += 1

    def release(self, tag: str) -> dict[str, Any] | None:
        result = run_command(
            ("gh", "api", f"repos/{self.repo}/releases/tags/{tag}"),
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        for release in self.list_releases():
            if release.get("tag_name") == tag:
                return release
        return None

    def create_draft(self, tag: str, title: str) -> dict[str, Any]:
        self.gh(
            "release",
            "create",
            tag,
            "--repo",
            self.repo,
            "--title",
            title,
            "--notes",
            "(生成中…)",
            "--draft",
        )
        for _ in range(6):
            release = self.release(tag)
            if release:
                return release
            time.sleep(2)
        raise ToolError(f"创建 draft 后无法读取 Release:{tag}")

    def publish(self, release: Mapping[str, Any]) -> None:
        self.api_json(
            f"repos/{self.repo}/releases/{release['id']}",
            method="PATCH",
            payload={"draft": False},
        )

    def upload(self, tag: str, paths: Sequence[Path], *, clobber: bool = False) -> None:
        if not paths:
            return
        args = ["release", "upload", tag, "--repo", self.repo]
        if clobber:
            args.append("--clobber")
        args.extend(str(path) for path in paths)
        self.gh(*args)

    def download(self, tag: str, directory: Path, pattern: str | None = None) -> None:
        args = ["release", "download", tag, "--repo", self.repo, "--dir", str(directory)]
        if pattern:
            args.extend(("--pattern", pattern, "--clobber"))
        self.gh(*args)

    def edit_notes(self, tag: str, notes: str, directory: Path) -> None:
        notes_file = directory / "notes.md"
        notes_file.write_text(notes, encoding="utf-8")
        self.gh("release", "edit", tag, "--repo", self.repo, "--notes-file", str(notes_file))


@dataclass(frozen=True)
class Candidate:
    url: str
    name: str


def validate_local_asset(path: Path, asset: Mapping[str, Any]) -> None:
    size = int(asset.get("size") or 0)
    if size and path.stat().st_size != size:
        raise ToolError(f"同名资产大小不同:{path.name}")
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:") and sha256_file(path) != digest.removeprefix("sha256:"):
        raise ToolError(f"同名资产 SHA256 不同:{path.name}")


def assets_match(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    if int(first.get("size") or 0) != int(second.get("size") or 0):
        return False
    first_digest = str(first.get("digest") or "")
    second_digest = str(second.get("digest") or "")
    return not (first_digest and second_digest) or first_digest == second_digest


class ReleaseMirror:
    def __init__(self, github: GitHub, http: HttpClient) -> None:
        self.github = github
        self.http = http

    def _load_checksums(self, tag: str, release: Mapping[str, Any], directory: Path) -> dict[str, str]:
        names = {str(asset["name"]) for asset in release.get("assets", [])}
        if CHECKSUM_NAME not in names:
            return {}
        try:
            self.github.download(tag, directory, CHECKSUM_NAME)
            return parse_checksums((directory / CHECKSUM_NAME).read_text(encoding="utf-8"))
        except (OSError, ToolError):
            return {}

    def ensure(
        self,
        tag: str,
        title: str,
        urls: Sequence[str],
    ) -> None:
        candidates = [Candidate(url, filename_from_url(url)) for url in urls if url]
        candidates = [candidate for candidate in candidates if candidate.name and self.http.exists(candidate.url)]
        if not candidates:
            log(f"  ⏭ {tag}: CDN 无资产,跳过")
            return

        release = self.github.release(tag)
        existing = {str(asset["name"]): asset for asset in (release or {}).get("assets", [])}
        with tempfile.TemporaryDirectory(prefix="mumu-release-") as temporary:
            directory = Path(temporary)
            checksums = self._load_checksums(tag, release, directory) if release else {}
            original_checksums = dict(checksums)
            upload: list[Path] = []
            split_info: dict[str, tuple[str, int]] = {}

            for candidate in candidates:
                existing_parts = sorted(
                    name for name in existing if name.startswith(f"{candidate.name}.part.")
                )
                if candidate.name in existing and candidate.name in checksums:
                    continue
                if existing_parts and all(name in checksums for name in existing_parts):
                    continue

                log(f"  📥 {tag} ← {candidate.name}")
                downloaded = directory / candidate.name
                self.http.download(candidate.url, downloaded)
                size = downloaded.stat().st_size
                if size > SPLIT_MAX:
                    parts, original_hash = split_file(downloaded)
                    split_info[candidate.name] = (original_hash, len(parts))
                    log(f"     ✂️ {size // 1_048_576}MB → 分成 {len(parts)} 卷")
                    for part in parts:
                        digest = sha256_file(part)
                        checksums[part.name] = digest
                        if part.name in existing:
                            validate_local_asset(part, existing[part.name])
                        else:
                            upload.append(part)
                else:
                    digest = sha256_file(downloaded)
                    checksums[candidate.name] = digest
                    if candidate.name in existing:
                        validate_local_asset(downloaded, existing[candidate.name])
                    else:
                        upload.append(downloaded)
                    log(f"     ✅ {size // 1_048_576} MB")

            if not release and not upload:
                raise ToolError(f"{tag}:没有可创建 Release 的资产")
            if release and not upload and checksums == original_checksums and not release.get("draft"):
                checksum_text = format_checksums(checksums)
                notes = build_release_notes(release.get("assets", []), checksum_text)
                if notes != str(release.get("body") or ""):
                    self.github.edit_notes(tag, notes, directory)
                    log(f"  📝 {tag}: 已更新说明")
                log(f"  ⏭ {tag}: 已完整,跳过")
                return

            if not release:
                release = self.github.create_draft(tag, title)

            self.github.upload(tag, upload)
            refreshed = self.github.release(tag)
            if not refreshed:
                raise ToolError(f"上传后无法读取 Release:{tag}")
            refreshed_assets = {str(asset["name"]): asset for asset in refreshed.get("assets", [])}
            for path in upload:
                if path.name not in refreshed_assets:
                    raise ToolError(f"上传后缺少资产:{path.name}")
                validate_local_asset(path, refreshed_assets[path.name])

            final_names = set(refreshed_assets) - {CHECKSUM_NAME}
            filtered_checksums = {name: digest for name, digest in checksums.items() if name in final_names}
            checksum_text = format_checksums(filtered_checksums)
            checksum_path = directory / CHECKSUM_NAME
            checksum_path.write_text(checksum_text, encoding="utf-8")
            self.github.upload(tag, [checksum_path], clobber=True)

            refreshed = self.github.release(tag)
            if not refreshed:
                raise ToolError(f"生成说明前无法读取 Release:{tag}")
            notes = build_release_notes(refreshed.get("assets", []), checksum_text, split_info)
            self.github.edit_notes(tag, notes, directory)
            if refreshed.get("draft"):
                self.github.publish(refreshed)
            log(f"  ✅ {tag} 就绪(新增 {len(upload)} 个资产)")


@dataclass(frozen=True)
class PrivateSyncAPI:
    repo: str
    cdn: str
    http: HttpClient
    mirror: ReleaseMirror
    tool_error: type[ToolError] = ToolError
    extract_version: Any = extract_version
    version_key: Any = version_key
    filename_from_url: Any = filename_from_url
    require_env: Any = require_env
    mask_source_hosts: Any = mask_source_hosts
    log: Any = log


_PRIVATE_PLUGIN: dict[str, Any] | None = None


def private_plugin() -> dict[str, Any]:
    global _PRIVATE_PLUGIN
    if _PRIVATE_PLUGIN is not None:
        return _PRIVATE_PLUGIN
    encoded = require_env("MUMU_SYNC_PLUGIN_B64")
    try:
        source = base64.b64decode(encoded, validate=True).decode("utf-8")
        namespace: dict[str, Any] = {"__builtins__": __builtins__}
        exec(compile(source, "<private-sync-plugin>", "exec"), namespace)
    except Exception as error:
        raise ToolError(f"私有同步扩展加载失败({type(error).__name__})") from None
    _PRIVATE_PLUGIN = namespace
    return namespace


def run_private_sync(mode: str) -> None:
    runner = private_plugin().get("run_sync")
    if not callable(runner):
        raise ToolError("私有同步扩展缺少 run_sync")
    repo = require_env("GITHUB_REPOSITORY")
    cdn = require_env("MUMU_CDN").rstrip("/")
    http = HttpClient()
    api = PrivateSyncAPI(repo, cdn, http, ReleaseMirror(GitHub(repo), http))
    runner(mode, api)


def private_sort_rules() -> Mapping[str, Any]:
    provider = private_plugin().get("sort_rules")
    if not callable(provider):
        raise ToolError("私有同步扩展缺少 sort_rules")
    rules = provider()
    if not isinstance(rules, Mapping):
        raise ToolError("私有排序规则格式无效")
    return rules


@dataclass
class OrderRecord:
    source_epoch: int
    version: str
    tag: str
    sort_epoch: int = 0
    marker_epoch: int = 0


def order_records(
    records: Sequence[OrderRecord],
    legacy_anchor: int,
    legacy_tags: Sequence[str],
    fallback_epoch: int,
) -> list[OrderRecord]:
    legacy_ranks = {tag: index + 1 for index, tag in enumerate(legacy_tags)}
    prepared = []
    for record in records:
        sort_epoch = record.source_epoch
        if not sort_epoch:
            sort_epoch = legacy_anchor - legacy_ranks[record.tag] if record.tag in legacy_ranks else fallback_epoch
        prepared.append(OrderRecord(record.source_epoch, record.version, record.tag, sort_epoch))
    prepared.sort(key=lambda item: (item.sort_epoch, version_key(item.version), item.tag), reverse=True)

    previous_epoch: int | None = None
    previous_day = None
    for record in prepared:
        marker = record.sort_epoch
        marker_day = datetime.fromtimestamp(marker, UTC).date()
        if previous_day is not None and marker_day >= previous_day:
            marker = int(previous_epoch or marker) - 86_400
            marker_day = datetime.fromtimestamp(marker, UTC).date()
        record.marker_epoch = marker
        previous_epoch, previous_day = marker, marker_day
    return prepared


class ReleaseOrderer:
    def __init__(self) -> None:
        self.repo = require_env("GITHUB_REPOSITORY")
        self.cdn = require_env("MUMU_CDN").rstrip("/")
        self.github = GitHub(self.repo)
        self.http = HttpClient()
        self.rules = private_sort_rules()

    @staticmethod
    def _git(*args: str, check: bool = True, env: Mapping[str, str] | None = None, input_text: str | None = None) -> str:
        return run_command(("git", *args), check=check, env=env, input_text=input_text).stdout.strip()

    def _saved_source_epoch(self, tag: str) -> int:
        message = self._git("show", "-s", "--format=%B", f"{tag}^{{commit}}", check=False)
        matches = re.findall(r"^source-last-modified: (\d+)$", message, re.MULTILINE)
        return int(matches[-1]) if matches else 0

    def _source_epoch(self, names: Sequence[str]) -> int:
        newest = 0
        for name in names:
            source_name = re.sub(r"\.part\.[a-z][a-z]$", "", name)
            headers = self.http.head(f"{self.cdn}/{source_name}")
            if not headers:
                continue
            modified = next((value for key, value in headers.items() if key.lower() == "last-modified"), "")
            if not modified:
                continue
            try:
                epoch = int(parsedate_to_datetime(modified).timestamp())
            except (TypeError, ValueError, OverflowError):
                continue
            newest = max(newest, epoch)
        return newest

    def collect(self) -> list[OrderRecord]:
        records = []
        for release in self.github.list_releases():
            if release.get("draft") or release.get("prerelease"):
                continue
            tag = str(release["tag_name"])
            names = sorted(
                {
                    str(asset["name"])
                    for asset in release.get("assets", [])
                    if asset.get("name") != CHECKSUM_NAME
                }
            )
            source_epoch = self._source_epoch(names) or self._saved_source_epoch(tag)
            records.append(OrderRecord(source_epoch, extract_version(tag) or "0", tag))
        anchor_tag = str(self.rules.get("legacy_anchor_tag") or "")
        fallback_epoch = int(self.rules.get("fallback_epoch") or 0)
        legacy_tags = tuple(str(tag) for tag in self.rules.get("legacy_mac_tags") or ())
        if not anchor_tag or fallback_epoch <= 0:
            raise ToolError("私有排序规则缺少锚点")
        anchor = next(
            (record.source_epoch for record in records if record.tag == anchor_tag),
            fallback_epoch,
        )
        return order_records(records, anchor or fallback_epoch, legacy_tags, fallback_epoch)

    def update_tags(self, records: Sequence[OrderRecord]) -> int:
        parent = self._git("rev-parse", "origin/main")
        clean_tree = self._git("rev-parse", "origin/main^{tree}")
        changed = 0
        updates = []
        for record in records:
            current = self._git("rev-parse", f"{record.tag}^{{commit}}")
            current_epoch = int(self._git("show", "-s", "--format=%ct", current))
            current_source = self._saved_source_epoch(record.tag)
            current_tree = self._git("rev-parse", f"{record.tag}^{{tree}}")
            if (
                current_epoch == record.marker_epoch
                and current_source == record.source_epoch
                and current_tree == clean_tree
            ):
                log(f"✓ {record.tag:<32} source={record.source_epoch} version={record.version}")
                continue
            identity = {
                **os.environ,
                "GIT_AUTHOR_NAME": "github-actions[bot]",
                "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                "GIT_AUTHOR_DATE": f"@{record.marker_epoch} +0000",
                "GIT_COMMITTER_NAME": "github-actions[bot]",
                "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                "GIT_COMMITTER_DATE": f"@{record.marker_epoch} +0000",
            }
            message = f"release-order: {record.tag}\nsource-last-modified: {record.source_epoch}\n"
            marker = self._git("commit-tree", clean_tree, "-p", parent, env=identity, input_text=message)
            self._git("tag", "-f", record.tag, marker)
            updates.append(f"refs/tags/{record.tag}")
            changed += 1
            log(f"↻ {record.tag:<32} source={record.source_epoch} version={record.version}")
        if updates:
            self._git("push", "--force", "origin", *updates)
            log(f"↑ 已批量更新 {len(updates)} 个 tag")
        return changed

    @staticmethod
    def _asset_snapshot(release: Mapping[str, Any]) -> list[tuple[str, int, str]]:
        return sorted(
            (
                str(asset["name"]),
                int(asset.get("size") or 0),
                str(asset.get("digest") or ""),
            )
            for asset in release.get("assets", [])
        )

    def rebuild(self, tag: str) -> None:
        release = self.github.release(tag)
        if not release:
            raise ToolError(f"待重建 Release 不存在:{tag}")
        before = self._asset_snapshot(release)
        with tempfile.TemporaryDirectory(prefix="mumu-sort-") as temporary:
            directory = Path(temporary)
            assets_dir = directory / "assets"
            assets_dir.mkdir()
            self.github.download(tag, assets_dir)
            notes = str(release.get("body") or "")
            notes_file = directory / "notes.md"
            notes_file.write_text(notes, encoding="utf-8")
            title = str(release.get("name") or tag)
            prerelease = bool(release.get("prerelease"))
            self.github.gh("release", "delete", tag, "--repo", self.repo, "--yes")
            args = [
                "release",
                "create",
                tag,
                "--repo",
                self.repo,
                "--verify-tag",
                "--title",
                title,
                "--notes-file",
                str(notes_file),
                "--latest=false",
            ]
            if prerelease:
                args.append("--prerelease")
            args.extend(str(path) for path in sorted(assets_dir.iterdir()))
            try:
                self.github.gh(*args)
            except ToolError:
                if not self.github.release(tag):
                    self.github.gh(*args)
                raise
            rebuilt = self.github.release(tag)
            if not rebuilt or self._asset_snapshot(rebuilt) != before:
                raise ToolError(f"{tag} 重建后的附件清单不一致")
        log(f"↻ {tag:<32} 刷新网页排序索引")

    def run(self) -> None:
        self._git("fetch", "--force", "--tags", "origin")
        records = self.collect()
        if not records:
            log("⏭ 无 release,跳过")
            return
        changed = self.update_tags(records)
        target = [record.tag for record in records]
        rebuilt = 0
        while True:
            actual = [
                str(release["tag_name"])
                for release in self.github.list_releases()
                if not release.get("draft") and not release.get("prerelease")
            ]
            if actual == target:
                break
            mismatch = next((current for expected, current in zip(target, actual) if expected != current), "")
            if not mismatch or rebuilt >= len(target):
                raise ToolError("无法收敛 GitHub Releases 网页顺序")
            self.rebuild(mismatch)
            rebuilt += 1
        newest = target[0]
        self.github.gh("release", "edit", newest, "--repo", self.repo, "--latest")
        log(f"✅ Release 排序完成:更新 {changed} 个 tag,重建 {rebuilt} 个错位项; Latest={newest}")


def merge_release(source_tag: str, target_tag: str) -> None:
    if source_tag == target_tag:
        raise ToolError("源和目标 tag 不能相同")
    repo = require_env("GITHUB_REPOSITORY")
    github = GitHub(repo)
    source = github.release(source_tag)
    target = github.release(target_tag)
    if not source or not target:
        raise ToolError("源或目标 Release 不存在")

    with tempfile.TemporaryDirectory(prefix="mumu-merge-") as temporary:
        work = Path(temporary)
        source_dir, target_dir = work / "source", work / "target"
        source_dir.mkdir()
        target_dir.mkdir()
        github.download(source_tag, source_dir)
        try:
            github.download(target_tag, target_dir, CHECKSUM_NAME)
        except ToolError:
            pass

        source_assets = {str(asset["name"]): asset for asset in source.get("assets", [])}
        target_assets = {str(asset["name"]): asset for asset in target.get("assets", [])}
        upload = []
        for path in sorted(source_dir.iterdir()):
            if path.name == CHECKSUM_NAME:
                continue
            if path.name in target_assets:
                source_record = source_assets[path.name]
                target_record = target_assets[path.name]
                if not assets_match(source_record, target_record):
                    raise ToolError(f"目标已存在同名但内容不同的附件:{path.name}")
            else:
                upload.append(path)
        github.upload(target_tag, upload)

        checksums = {}
        target_checksum = target_dir / CHECKSUM_NAME
        source_checksum = source_dir / CHECKSUM_NAME
        if target_checksum.exists():
            checksums.update(parse_checksums(target_checksum.read_text(encoding="utf-8")))
        if source_checksum.exists():
            checksums.update(parse_checksums(source_checksum.read_text(encoding="utf-8")))
        for path in source_dir.iterdir():
            if path.is_file() and path.name != CHECKSUM_NAME:
                checksums[path.name] = sha256_file(path)
        checksum_text = format_checksums(checksums)
        merged_checksum = work / CHECKSUM_NAME
        merged_checksum.write_text(checksum_text, encoding="utf-8")
        github.upload(target_tag, [merged_checksum], clobber=True)

        merged = github.release(target_tag)
        if not merged:
            raise ToolError("合并后无法读取目标 Release")
        merged_assets = {str(asset["name"]): asset for asset in merged.get("assets", [])}
        for name, source_asset in source_assets.items():
            if name == CHECKSUM_NAME:
                continue
            target_asset = merged_assets.get(name)
            if not target_asset or not assets_match(source_asset, target_asset):
                raise ToolError(f"附件校验失败:{name}")
        notes = build_release_notes(merged.get("assets", []), checksum_text)
        github.edit_notes(target_tag, notes, work)
        github.gh("release", "delete", source_tag, "--repo", repo, "--yes", "--cleanup-tag")
        log(f"✅ {source_tag} 已并入 {target_tag}")


def cleanup_runs() -> None:
    repo = require_env("GITHUB_REPOSITORY")
    current_run = int(require_env("GITHUB_RUN_ID"))
    github = GitHub(repo)
    runs: list[Mapping[str, Any]] = []
    page = 1
    while True:
        payload = github.api_json(f"repos/{repo}/actions/runs?per_page=100&page={page}")
        batch = payload.get("workflow_runs", []) if isinstance(payload, Mapping) else []
        if not isinstance(batch, list):
            raise ToolError("GitHub Actions 响应格式错误")
        runs.extend(run for run in batch if isinstance(run, Mapping))
        if len(batch) < 100:
            break
        page += 1

    deleted = 0
    for run in runs:
        run_id = int(run.get("id") or 0)
        if not run_id or run_id == current_run or run.get("status") != "completed":
            continue
        github.api_json(f"repos/{repo}/actions/runs/{run_id}", method="DELETE")
        deleted += 1
    log(f"✅ 已清理 {deleted} 条旧 Actions 记录,保留当前运行 {current_run}")


def jitter(max_seconds: int) -> None:
    delay = secrets.randbelow(max_seconds + 1)
    log(f"本次随机延迟 {delay} 秒")
    time.sleep(delay)


def keepalive(days_threshold: int) -> None:
    last = int(run_command(("git", "log", "-1", "--format=%ct")).stdout.strip())
    days = (int(time.time()) - last) // 86_400
    log(f"距上次提交 {days} 天")
    if days < days_threshold:
        log(f"⏭ 无需 keepalive (< {days_threshold} 天)")
        return
    run_command(("git", "config", "user.name", "github-actions[bot]"))
    run_command(
        ("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    )
    # 仓库历史固定为单根提交；keepalive 只刷新该提交，不累积空提交。
    run_command(("git", "commit", "--allow-empty", "--amend", "--no-edit"))
    run_command(("git", "push", "--force-with-lease", "origin", "HEAD:main"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="同步官方安装包")
    sync_parser.add_argument(
        "mode",
        choices=(
            "mac-current",
            "win-offline",
            "win-full",
            "win-installer",
            "win-arm-current",
            "windows",
            "all",
        ),
    )

    subparsers.add_parser("sort-releases", help="按 CDN 源文件时间重排 Releases")
    merge_parser = subparsers.add_parser("merge-release", help="合并两个 Release")
    merge_parser.add_argument("source_tag")
    merge_parser.add_argument("target_tag")

    subparsers.add_parser("cleanup-runs", help="删除当前运行之外的旧 Actions 记录")

    jitter_parser = subparsers.add_parser("jitter", help="定时任务随机错峰")
    jitter_parser.add_argument("--max-seconds", type=int, default=1800)

    keepalive_parser = subparsers.add_parser("keepalive", help="避免定时 workflow 因仓库不活跃被禁用")
    keepalive_parser.add_argument("--days", type=int, default=50)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "sync":
            run_private_sync(args.mode)
        elif args.command == "sort-releases":
            ReleaseOrderer().run()
        elif args.command == "merge-release":
            merge_release(args.source_tag, args.target_tag)
        elif args.command == "cleanup-runs":
            cleanup_runs()
        elif args.command == "jitter":
            jitter(args.max_seconds)
        elif args.command == "keepalive":
            keepalive(args.days)
        return 0
    except ToolError as error:
        print(f"❌ {error}", file=sys.stderr)
        return 1
    except Exception as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        location = f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        print(f"❌ 操作失败({type(error).__name__}, {location})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
