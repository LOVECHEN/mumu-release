#!/usr/bin/env python3
"""MuMu 官方安装包镜像、Release 合并与排序工具。"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


USER_AGENT = "Mozilla/5.0"
SPLIT_MAX = 1_992_294_400  # 1900 MiB，低于 GitHub Release 单文件 2 GiB 上限。
CHECKSUM_NAME = "checksums.sha256"
NX_PATH = "/api/v2/download/nx"
FALLBACK_VERSION = "6.8.0"
FALLBACK_FILES = (
    "MuMu-setup-mumu15-V15.8.0.5677-overseas-0923052014.exe",
    "MuMu-setup-nemux-V12.8.0.5676-overseas-0923051918.exe",
    "MuMu-setup-nxmain-V1.8.0.5675-overseas-0923051933.exe",
)
LEGACY_MAC_TAGS = (
    "mac-1.4.22",
    "mac-1.4.18",
    "mac-1.4.11",
    "mac-1.4.10",
    "mac-1.4.5",
)


@dataclass(frozen=True)
class ReleaseHistory:
    published: str
    summary: str
    source_url: str = ""
    status: str = "official"


@dataclass(frozen=True)
class HistoricalRelease:
    version: str
    filenames: tuple[str, ...]
    history: ReleaseHistory | None = None


WINDOWS_X64_BACKFILL = (
    HistoricalRelease("5.14.2", ("MuMu-setup-V5.14.2.2667-1230164527.exe",)),
    HistoricalRelease(
        "5.21.1",
        ("MuMu-setup-V5.21.1.3007-0129002129.exe",),
        ReleaseHistory(
            "2026-01-29",
            "新增掌上 MuMu 远控，优化游戏体验并修复安卓设备删除问题。",
            "https://mumu.163.com/20260129/38646_1284453.html",
        ),
    ),
    HistoricalRelease(
        "5.22.0",
        ("MuMu-setup-V5.22.0.3094-0207004753.exe",),
        ReleaseHistory(
            "2026-02-08",
            "新增桌面整理、加速后启动 App 和双击 APK 选择设备等功能。",
            "https://mumu.163.com/20260208/38646_1285979.html",
        ),
    ),
    HistoricalRelease(
        "5.24.5",
        ("MuMu-setup-V5.24.5.3354-0410235315.exe",),
        ReleaseHistory(
            "2026-04-14",
            "优化远控及部分游戏体验。",
            "https://mumu.163.com/20260414/38646_1296032.html",
        ),
    ),
    HistoricalRelease(
        "5.27.1",
        ("MuMu-setup-V5.27.1.3518-0430192241.exe",),
        ReleaseHistory(
            "2026-04-30",
            "修复安卓设备启动响应慢，优化部分游戏体验。",
            "https://mumu.163.com/20260430/38646_1298829.html",
        ),
    ),
    HistoricalRelease(
        "5.27.4",
        ("MuMu-setup-V5.27.4.3536-0501223852.exe",),
        ReleaseHistory(
            "2026-05-02",
            "修复安卓设备启动响应慢，优化部分游戏体验。",
            "https://mumu.163.com/20260506/38646_1299137.html",
        ),
    ),
    HistoricalRelease("6.0.1", ("MuMu_6.0.1_gw-win_zh-Hans_1783047114.exe",)),
    HistoricalRelease("6.2.5", ("MuMu-setup-V5.30.1.3586-0523181240.exe",)),
    HistoricalRelease(
        "6.5.4",
        (
            "MuMu-setup-mumu15-V15.5.4.5061-0819115936.exe",
            "MuMu-setup-nemux-V12.5.4.5060-0819115508.exe",
        ),
    ),
)

WINDOWS_ARM_HISTORY = {
    "1.6.9": ReleaseHistory(
        "2025-05-07",
        "优化部分游戏体验并修复已知问题。",
        "https://mumu.163.com/20250507/41817_1232690.html",
    ),
    "1.6.10": ReleaseHistory(
        "2025-05-22",
        "新增全屏手势，优化触摸板滚动响应并修复已知问题。",
        "https://mumu.163.com/20250522/41817_1236199.html",
    ),
    "1.6.11": ReleaseHistory(
        "2025-05-27",
        "优化键鼠手柄体验并修复已知问题。",
        "https://mumu.163.com/20250527/41817_1236812.html",
    ),
    "1.6.14": ReleaseHistory(
        "2025-06-20",
        "新增返回上一级全屏手势，修复输入法崩溃等问题。",
        "https://mumu.163.com/20250620/41817_1241930.html",
    ),
    "1.6.16": ReleaseHistory(
        "2025-07-11",
        "修复部分已知问题。",
        "https://mumu.163.com/20250711/41817_1246672.html",
    ),
    "1.8.5": ReleaseHistory(
        "2026-05-01",
        "修复部分已知问题。",
        "https://mumu.163.com/20260501/41817_1298888.html",
    ),
}

WINDOWS_ARM_PATTERNS = (
    "MuMuARM_{version}_gw-arm-beta.exe",
    "MuMuARM_{version}_gw-update-armbeta.exe",
    "MuMuPlayerARM_{version}_gw-arm-beta.exe",
    "MuMuPlayerARM_{version}_gw-update-armbeta.exe",
)


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
    patterns = (
        (r"_default\.dmg$", "🍎 全量 中国版 (Apple Silicon · dmg)"),
        (r"_global\.dmg$", "🍎 全量 国际版 (Apple Silicon · dmg)"),
        (r"^MuMuPlayerPro-v.*-global\.dmg$", "🍎 全量 国际版 (Apple Silicon · dmg)"),
        (r"^MuMuPlayerPro-v.*\.dmg$", "🍎 全量 中国版 (Apple Silicon · dmg)"),
        (r"^MuMuPlayer_.*_default\.tar\.gz$", "🍎 完整包 中国版 (Apple Silicon · tar.gz)"),
        (r"^MuMuPlayer_.*_global\.tar\.gz$", "🍎 完整包 国际版 (Apple Silicon · tar.gz)"),
        (r"^MuMuUpdater_.*_default\.tar\.gz$", "🍎 完整包 中国版 (Apple Silicon · tar.gz)"),
        (r"^MuMuMacUpdater_.*-global\.tar\.gz$", "🍎 完整包 国际版 (Apple Silicon · tar.gz)"),
        (r"^(?:MuMu|MuMuPlayer)ARM_.*\.exe$", "🪟 Windows ARM 官方安装包 (ARM64 · exe)"),
        (r"(?:gw-win|gwwin)_.*\.exe$", "🪟 在线安装器 中国版 (64-bit · exe)"),
        (r"(?:gw-win-download_|gw-overseas12_).*\.exe$", "🪟 在线安装器 国际版 (64-bit · exe)"),
        (r"mumu15.*overseas.*\.exe$", "🪟 完整离线安装包 国际版 · 安卓15 (mumu15,默认)"),
        (r"nemux.*overseas.*\.exe$", "🪟 完整离线安装包 国际版 · 安卓12 (nemux)"),
        (r"nxmain.*overseas.*\.exe$", "🪟 完整离线安装包 国际版 · NX主引擎 (nxmain)"),
        (r"overseas.*\.exe$", "🪟 完整离线安装包 国际版 (64-bit · exe)"),
        (r"^MuMu-setup-mumu15-.*\.exe$", "🪟 完整离线安装包 中国版 · 安卓15 (mumu15,默认)"),
        (r"^MuMu-setup-nemux-.*\.exe$", "🪟 完整离线安装包 中国版 · 安卓12 (nemux)"),
        (r"^MuMu-setup-nxmain-.*\.exe$", "🪟 完整离线安装包 中国版 · NX主引擎 (nxmain)"),
        (r"^(?:MuMu-setup-V|MuMuNG-setup-).*\.exe$", "🪟 完整离线安装包 中国版 · 合体版 (64-bit · exe)"),
        (r"^MuMu-setup-.*\.exe$", "🪟 完整离线安装包 中国版 (64-bit · exe)"),
        (r"\.part\.[a-z][a-z]$", "🧩 分卷片段(需合并,见下方说明)"),
    )
    for pattern, label in patterns:
        if re.search(pattern, name):
            return label
    return "安装包"


def build_release_notes(
    assets: Sequence[Mapping[str, Any]],
    checksum_text: str,
    split_info: Mapping[str, tuple[str, int]] | None = None,
    history: ReleaseHistory | None = None,
) -> str:
    lines = []
    if history:
        lines.extend(("### 版本信息", "", f"- 发布日期：{history.published}"))
        if history.summary:
            lines.append(f"- 更新内容：{history.summary}")
        if history.status == "cdn-candidate":
            lines.append("- 状态：网易 CDN 已存在，官网当前下载入口尚未切换到此版本。")
        elif history.status == "cdn-only":
            lines.append("- 状态：网易 CDN 文件已验证，未找到对应的官方更新公告。")
        if history.source_url:
            lines.append(f"- 官方记录：[{history.source_url}]({history.source_url})")
        lines.append("")
    lines.extend(("### 下载文件", "", "| 类型 | 文件 | 大小 |", "|------|------|------|"))
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
        history: ReleaseHistory | None = None,
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
                if history:
                    checksum_text = format_checksums(checksums)
                    notes = build_release_notes(
                        release.get("assets", []), checksum_text, history=history
                    )
                    if notes != str(release.get("body") or ""):
                        self.github.edit_notes(tag, notes, directory)
                        log(f"  📝 {tag}: 已补版本信息")
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
            notes = build_release_notes(
                refreshed.get("assets", []), checksum_text, split_info, history
            )
            self.github.edit_notes(tag, notes, directory)
            if refreshed.get("draft"):
                self.github.publish(refreshed)
            log(f"  ✅ {tag} 就绪(新增 {len(upload)} 个资产)")


MACHINE = {
    "base_board": "Manufacturer:ASUSTeK COMPUTER INC.Product:PRIME B550M-A",
    "cpu": "AMD Ryzen 5 5600G with Radeon Graphics",
    "hard_disk": ["DRIVE_FIXED(C:\\):Total disk space:476.9GBFree disk space:210.3GB"],
    "hyperv_opened": 0,
    "ip": "1.2.3.4",
    "mac": "AA:BB:CC:DD:EE:FF",
    "memory": 16000,
    "os": "Windows 11 64-bit Kernel 10.0.22631",
    "screen": {"height": 1080, "width": 1920},
    "screen_list": [{"dpr": 1, "height": 1080, "is_primary": 1, "width": 1920}],
    "supported_install_arc": "x86_64",
    "video": ["NVIDIA GeForce RTX 3060"],
    "vt": "Intel/AMD virtualization technology detected.",
    "vt_enabled": 1,
    "vt_supported": 1,
}
MACHINE_STRING = json.dumps(MACHINE, sort_keys=True, separators=(", ", ": "), ensure_ascii=False)


@dataclass(frozen=True)
class NxRegion:
    host_env: str
    channel: str
    downloader_version: str
    usage: str
    language: str
    country: str
    package: str


NX_REGIONS = {
    "global": NxRegion(
        "MUMU_NX_HOST_GL", "gw-overseas12", "6.0.2", "1", "en", "US", "com.netease.mumu.nx"
    ),
    "cn": NxRegion("MUMU_NX_HOST_CN", "gw-win", "6.0.3", "0", "zh-Hans", "CN", "com.netease.mumu"),
}


def nx_headers(client_id: str, region: NxRegion, timestamp_ms: int, nonce: str) -> dict[str, str]:
    version = region.downloader_version
    return {
        "X-Param-PLAT": "1",
        "X-Param-NG": "NXMAIN",
        "X-Param-client-id": client_id,
        "X-Param-UUID": client_id,
        "X-Param-VN": version,
        "X-Param-VC": version.replace(".", ""),
        "X-Param-PKGN": region.package,
        "X-Param-CHN": region.channel,
        "X-Param-FCHN": region.channel,
        "X-Param-LANG": region.language,
        "X-Param-CNT": region.country,
        "X-Param-TS": str(timestamp_ms),
        "X-Param-System-ID": client_id,
        "X-Param-NONCE": nonce,
        "X-Param-ENT": "",
        "X-Param-user-id": "",
        "X-Param-device-id": "",
        "X-Param-TDID": "",
        "X-Param-OAID": "",
        "X-Param-PRODUCT": "NX",
        "X-Param-PRODUCT-VN": version,
        "X-Param-CAMPAIGN": "",
        "X-Param-ARCH": "x86_64",
        "X-Param-TZ-OFFSET": "-480",
    }


def nx_signature(secret: bytes, headers: Mapping[str, str], encoded_body: str) -> str:
    items = sorted(
        ((key, value) for key, value in headers.items() if key.lower().startswith("x-param-")),
        key=lambda item: item[0].lower(),
    )
    message = "POST" + NX_PATH + "&".join(f"{key.lower()}={value}" for key, value in items) + encoded_body
    return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()


def discover_nx(region_name: str, http: HttpClient) -> tuple[str, list[str]]:
    if region_name not in NX_REGIONS:
        raise ToolError(f"未知地区:{region_name}")
    region = NX_REGIONS[region_name]
    secret = require_env("MUMU_NX_SECRET").encode()
    host = require_env(region.host_env)
    cdn = require_env("MUMU_CDN").rstrip("/")
    client_id = str(uuid.uuid4())
    fields = {
        "architecture": "x86_64",
        "channel": region.channel,
        "detectinfo": "",
        "downloader_version": region.downloader_version,
        "has_installed": "0",
        "language": region.language,
        "machine": MACHINE_STRING,
        "n": "MuMu_setup",
        "package": "",
        "product": "",
        "usage": region.usage,
        "uuid": client_id,
    }
    encoded = urllib.parse.urlencode(fields)
    headers = nx_headers(client_id, region, int(time.time() * 1000), uuid.uuid4().hex[:16])
    headers["X-Param-SIGN"] = nx_signature(secret, headers, encoded)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = http.post_form_json(f"https://{host}{NX_PATH}", fields, headers)
    if response.get("errcode") != 100:
        # errmsg 由远端控制，可能回显请求内容；Actions 日志只记录业务错误码。
        raise ToolError(f"nx 业务错误({region_name}):{response.get('errcode')}")
    data = response.get("data") or {}
    components = data.get("components") or []
    urls = []
    for component in components:
        name = filename_from_url(str(component.get("link") or ""))
        if name:
            urls.append(f"{cdn}/{name}")
    if not urls:
        raise ToolError(f"nx 未返回组件({region_name})")
    return str(data.get("version") or ""), urls


class Synchronizer:
    def __init__(self) -> None:
        self.repo = require_env("GITHUB_REPOSITORY")
        self.cdn = require_env("MUMU_CDN").rstrip("/")
        self.http = HttpClient()
        self.github = GitHub(self.repo)
        self.mirror = ReleaseMirror(self.github, self.http)
        self.mac_cn = os.environ.get("MUMU_DL_MAC_CN", "")
        self.mac_global = os.environ.get("MUMU_DL_MAC_GL", "")
        self.win_cn = os.environ.get("MUMU_DL_WIN_CN", "")
        self.win_global = os.environ.get("MUMU_DL_WIN_GL", "")
        self.win_arm = os.environ.get("MUMU_DL_WIN_ARM", "")
        self.win_full_index = os.environ.get("MUMU_WINFULL_INDEX", "")
        mask_source_hosts(
            (
                self.cdn,
                self.mac_cn,
                self.mac_global,
                self.win_cn,
                self.win_global,
                self.win_arm,
                os.environ.get("MUMU_NX_HOST_GL", ""),
                os.environ.get("MUMU_NX_HOST_CN", ""),
                self.win_full_index,
            )
        )

    def mac_specs(self, version: str) -> list[str]:
        names = (
            f"MuMuPlayer_{version}_default.dmg",
            f"MuMuPlayer_{version}_global.dmg",
            f"MuMuPlayer_{version}_default.tar.gz",
            f"MuMuPlayer_{version}_global.tar.gz",
            f"MuMuUpdater_{version}_default.tar.gz",
            f"MuMuMacUpdater_{version}-global.tar.gz",
            f"MuMuPlayerPro-v{version}.dmg",
            f"MuMuPlayerPro-v{version}-global.dmg",
        )
        return [f"{self.cdn}/{name}" for name in names]

    def mac_current(self) -> None:
        versions = set()
        for endpoint in (self.mac_cn, self.mac_global):
            if endpoint:
                version = extract_version(urllib.parse.urlsplit(self.http.redirect_target(endpoint)).path)
                if version:
                    versions.add(version)
        for version in sorted(versions, key=version_key):
            log(f"═══ mac-{version} ═══")
            self.mirror.ensure(f"mac-{version}", f"macOS · MuMuPlayer Pro {version}", self.mac_specs(version))

    def mac_backfill(self) -> None:
        for minor in range(1, 10):
            for patch in range(61):
                version = f"1.{minor}.{patch}"
                urls = self.mac_specs(version)
                if any(self.http.exists(url) for url in urls):
                    log(f"═══ (backfill) mac-{version} ═══")
                    self.mirror.ensure(f"mac-{version}", f"macOS · MuMuPlayer Pro {version}", urls)

    def best_windows_url(self, base: str, channels: Sequence[str]) -> str:
        choices = []
        if not base:
            return ""
        for channel in channels:
            separator = "&" if "?" in base else "?"
            target = self.http.redirect_target(f"{base}{separator}channel={channel}")
            bare = target.split("?", 1)[0]
            version = extract_version(bare)
            if bare and "apinochannel" not in bare and version:
                choices.append((version_key(version), bare))
        return max(choices, default=((0,), ""))[1]

    def win_installer(self) -> None:
        cn = self.best_windows_url(self.win_cn, ("gw-win", "gwwin"))
        global_url = self.best_windows_url(
            self.win_global, ("gwwin", "gw-overseas12", "gw-win-download")
        )
        cn_version = extract_version(cn)
        global_version = extract_version(global_url)
        grouped: dict[str, list[str]] = {}
        if cn_version:
            grouped.setdefault(cn_version, []).append(cn)
        if global_version:
            grouped.setdefault(global_version, []).append(global_url)
        for version in sorted(grouped, key=version_key):
            log(f"═══ win-{version} (在线安装器) ═══")
            self.mirror.ensure(
                f"win-{version}",
                f"Windows · MuMu模拟器12 / MuMu Player 12 {version}",
                grouped[version],
            )

    def win_full(self) -> None:
        if not self.win_full_index:
            log("⏭ 未配置 MUMU_WINFULL_INDEX,跳过 win-full")
            return
        try:
            html = self.http.get_text(self.win_full_index)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            log("❌ 离线包索引拉取失败,跳过")
            return
        match = re.search(r"https?://[A-Za-z0-9.-]+/MuMu-setup-V[0-9.]+-[0-9]+\.exe", html)
        if not match:
            log("❌ 未解析到离线包,跳过")
            return
        url = match.group(0)
        product_match = re.search(r"V(\d+\.\d+\.\d+)", html)
        version = product_match.group(1) if product_match else extract_version(url)
        if not version:
            raise ToolError("合体版缺少产品版本")
        log(f"═══ win-{version}(中国合体版)═══")
        self.mirror.ensure(
            f"win-{version}",
            f"Windows · MuMu模拟器12 / MuMu Player 12 {version}",
            [url],
        )

    def win_offline(self) -> None:
        try:
            global_raw, global_urls = discover_nx("global", self.http)
            global_version = extract_version(global_raw)
        except Exception as error:
            log(f"  ⚠ nx 自动发现失败({type(error).__name__}),回退内置直链(v{FALLBACK_VERSION})")
            global_version = FALLBACK_VERSION
            global_urls = [f"{self.cdn}/{name}" for name in FALLBACK_FILES]
        try:
            cn_raw, cn_urls = discover_nx("cn", self.http)
            cn_version = extract_version(cn_raw)
        except Exception as error:
            log(f"  ⏭ CN nx 未发现({type(error).__name__}),CN 合体版仍由 win-full 覆盖")
            cn_version, cn_urls = "", []

        grouped: dict[str, list[str]] = {}
        if global_version:
            grouped.setdefault(global_version, []).extend(global_urls)
        if cn_version:
            grouped.setdefault(cn_version, []).extend(cn_urls)
        for version in sorted(grouped, key=version_key):
            urls = list(dict.fromkeys(grouped[version]))
            log(f"═══ win-{version}(CN+Global 共 {len(urls)} 个候选资产)═══")
            self.mirror.ensure(
                f"win-{version}",
                f"Windows · MuMu模拟器12 / MuMu Player 12 {version}",
                urls,
            )

    def _cdn_history(self, url: str, status: str) -> ReleaseHistory | None:
        headers = self.http.head(url)
        if not headers:
            return None
        modified = next(
            (value for key, value in headers.items() if key.lower() == "last-modified"), ""
        )
        try:
            published = parsedate_to_datetime(modified).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            published = "未知"
        return ReleaseHistory(published, "", status=status)

    def _arm_urls(self, version: str) -> list[str]:
        return [
            f"{self.cdn}/{pattern.format(version=version)}" for pattern in WINDOWS_ARM_PATTERNS
        ]

    def win_arm_current(self) -> None:
        if not self.win_arm:
            log("⏭ 未配置 MUMU_DL_WIN_ARM,跳过 Windows ARM")
            return
        try:
            html = self.http.get_text(self.win_arm)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            log("❌ Windows ARM 下载入口拉取失败,跳过")
            return
        names = re.findall(
            r"(?:MuMu|MuMuPlayer)ARM_\d+\.\d+\.\d+_[A-Za-z0-9_-]+\.exe", html
        )
        if not names:
            log("❌ Windows ARM 下载入口未解析到安装包,跳过")
            return
        name = names[0]
        version = extract_version(name)
        url = f"{self.cdn}/{name}"
        history = WINDOWS_ARM_HISTORY.get(version) or self._cdn_history(url, "official")
        log(f"═══ win-arm-{version} (官网当前版) ═══")
        self.mirror.ensure(
            f"win-arm-{version}",
            f"Windows ARM · MuMu 模拟器 {version}",
            [url],
            history,
        )

        parts = version.split(".")
        if len(parts) != 3:
            return
        major, minor, patch = (int(part) for part in parts)
        for candidate_patch in range(patch + 1, patch + 6):
            candidate_version = f"{major}.{minor}.{candidate_patch}"
            candidate_url = self._arm_urls(candidate_version)[0]
            history = self._cdn_history(candidate_url, "cdn-candidate")
            if not history:
                continue
            log(f"═══ win-arm-{candidate_version} (CDN 候选) ═══")
            self.mirror.ensure(
                f"win-arm-{candidate_version}",
                f"Windows ARM · MuMu 模拟器 {candidate_version}",
                [candidate_url],
                history,
            )

    def win_x64_backfill(self) -> None:
        for spec in WINDOWS_X64_BACKFILL:
            urls = [f"{self.cdn}/{name}" for name in spec.filenames]
            history = spec.history or self._cdn_history(urls[0], "cdn-only")
            log(f"═══ (backfill) win-{spec.version} ═══")
            self.mirror.ensure(
                f"win-{spec.version}",
                f"Windows · MuMu 模拟器 {spec.version}",
                urls,
                history,
            )

    def win_arm_backfill(self) -> None:
        for minor in range(5, 10):
            for patch in range(41):
                version = f"1.{minor}.{patch}"
                available = next(
                    (url for url in self._arm_urls(version) if self.http.exists(url)), ""
                )
                if not available:
                    continue
                history = WINDOWS_ARM_HISTORY.get(version) or self._cdn_history(
                    available, "cdn-only"
                )
                log(f"═══ (backfill) win-arm-{version} ═══")
                self.mirror.ensure(
                    f"win-arm-{version}",
                    f"Windows ARM · MuMu 模拟器 {version}",
                    [available],
                    history,
                )

    def run(self, mode: str) -> None:
        handlers = {
            "mac-current": self.mac_current,
            "mac-backfill": self.mac_backfill,
            "win-installer": self.win_installer,
            "win-full": self.win_full,
            "win-offline": self.win_offline,
            "win-arm-current": self.win_arm_current,
            "win-x64-backfill": self.win_x64_backfill,
            "win-arm-backfill": self.win_arm_backfill,
        }
        if mode in {"windows", "all"}:
            names = ["win-offline", "win-full", "win-installer", "win-arm-current"]
            if mode == "all":
                names.insert(0, "mac-current")
            for name in names:
                handlers[name]()
            return
        handlers[mode]()


@dataclass
class OrderRecord:
    source_epoch: int
    version: str
    tag: str
    sort_epoch: int = 0
    marker_epoch: int = 0


def order_records(records: Sequence[OrderRecord], legacy_anchor: int) -> list[OrderRecord]:
    legacy_ranks = {tag: index + 1 for index, tag in enumerate(LEGACY_MAC_TAGS)}
    prepared = []
    for record in records:
        sort_epoch = record.source_epoch
        if not sort_epoch:
            sort_epoch = legacy_anchor - legacy_ranks[record.tag] if record.tag in legacy_ranks else 946_684_800
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
        anchor = next((record.source_epoch for record in records if record.tag == "mac-1.4.32"), 946_684_800)
        return order_records(records, anchor or 946_684_800)

    def update_tags(self, records: Sequence[OrderRecord]) -> int:
        parent = self._git("rev-parse", "origin/main")
        changed = 0
        for record in records:
            current = self._git("rev-parse", f"{record.tag}^{{commit}}")
            current_epoch = int(self._git("show", "-s", "--format=%ct", current))
            current_source = self._saved_source_epoch(record.tag)
            if current_epoch == record.marker_epoch and current_source == record.source_epoch:
                log(f"✓ {record.tag:<32} source={record.source_epoch} version={record.version}")
                continue
            tree = self._git("rev-parse", f"{record.tag}^{{tree}}")
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
            marker = self._git("commit-tree", tree, "-p", parent, env=identity, input_text=message)
            self._git("tag", "-f", record.tag, marker)
            self._git("push", "--force", "origin", f"refs/tags/{record.tag}")
            changed += 1
            log(f"↑ {record.tag:<32} source={record.source_epoch} version={record.version}")
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
            "mac-backfill",
            "win-offline",
            "win-full",
            "win-installer",
            "win-arm-current",
            "win-x64-backfill",
            "win-arm-backfill",
            "windows",
            "all",
        ),
    )

    subparsers.add_parser("sort-releases", help="按 CDN 源文件时间重排 Releases")
    merge_parser = subparsers.add_parser("merge-release", help="合并两个 Release")
    merge_parser.add_argument("source_tag")
    merge_parser.add_argument("target_tag")

    subparsers.add_parser("cleanup-runs", help="删除当前运行之外的旧 Actions 记录")

    discover_parser = subparsers.add_parser("discover-nx", help="查询 NX 三引擎官方直链")
    discover_parser.add_argument("region", nargs="?", choices=("global", "cn"), default="global")

    jitter_parser = subparsers.add_parser("jitter", help="定时任务随机错峰")
    jitter_parser.add_argument("--max-seconds", type=int, default=1800)

    keepalive_parser = subparsers.add_parser("keepalive", help="避免定时 workflow 因仓库不活跃被禁用")
    keepalive_parser.add_argument("--days", type=int, default=50)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "sync":
            Synchronizer().run(args.mode)
        elif args.command == "sort-releases":
            ReleaseOrderer().run()
        elif args.command == "merge-release":
            merge_release(args.source_tag, args.target_tag)
        elif args.command == "cleanup-runs":
            cleanup_runs()
        elif args.command == "discover-nx":
            version, urls = discover_nx(args.region, HttpClient())
            print(f"VERSION={version}")
            print("\n".join(urls))
        elif args.command == "jitter":
            jitter(args.max_seconds)
        elif args.command == "keepalive":
            keepalive(args.days)
        return 0
    except ToolError as error:
        print(f"❌ {error}", file=sys.stderr)
        return 1
    except Exception as error:
        # 底层网络库异常常含完整 URL；未知失败只暴露异常类型，不输出正文或 traceback。
        print(f"❌ 操作失败({type(error).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
