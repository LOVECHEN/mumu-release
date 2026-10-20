#!/usr/bin/env bash
# 在 GitHub Actions runner 内把一个 Release 的附件并入另一个 Release。
# 校验全部附件的名称、大小和 digest 后才删除源 Release 及其 tag。
set -euo pipefail

SOURCE_TAG="${1:?usage: merge_release_assets.sh SOURCE_TAG TARGET_TAG}"
TARGET_TAG="${2:?usage: merge_release_assets.sh SOURCE_TAG TARGET_TAG}"
REPO="${GITHUB_REPOSITORY:?need GITHUB_REPOSITORY}"
[ "$SOURCE_TAG" != "$TARGET_TAG" ] || { echo "源和目标 tag 不能相同" >&2; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/source" "$WORK/target" "$WORK/merged"

source_json=$(gh api "repos/$REPO/releases/tags/$SOURCE_TAG")
target_json=$(gh api "repos/$REPO/releases/tags/$TARGET_TAG")
title=$(printf '%s' "$target_json" | jq -r '.name')

gh release download "$SOURCE_TAG" --repo "$REPO" --dir "$WORK/source"
if ! gh release download "$TARGET_TAG" --repo "$REPO" \
  --pattern checksums.sha256 --dir "$WORK/target" --clobber; then
  : > "$WORK/target/checksums.sha256"
fi

cat "$WORK/target/checksums.sha256" "$WORK/source/checksums.sha256" \
  | awk 'NF && !seen[$0]++' > "$WORK/merged/checksums.sha256"

mapfile -d '' source_assets < <(
  find "$WORK/source" -maxdepth 1 -type f ! -name checksums.sha256 -print0
)
upload=()
for path in "${source_assets[@]}"; do
  name=$(basename "$path")
  source_digest=$(printf '%s' "$source_json" \
    | jq -r --arg name "$name" '.assets[] | select(.name == $name) | .digest')
  target_digest=$(printf '%s' "$target_json" \
    | jq -r --arg name "$name" '.assets[] | select(.name == $name) | .digest' | head -1)
  if [ -n "$target_digest" ] && [ "$target_digest" != "$source_digest" ]; then
    echo "目标已存在同名但内容不同的附件:$name" >&2
    exit 1
  fi
  [ -n "$target_digest" ] || upload+=("$path")
done

if [ "${#upload[@]}" -gt 0 ]; then
  gh release upload "$TARGET_TAG" --repo "$REPO" "${upload[@]}"
fi
gh release upload "$TARGET_TAG" --repo "$REPO" --clobber "$WORK/merged/checksums.sha256"

merged_json=$(gh api "repos/$REPO/releases/tags/$TARGET_TAG")
for path in "${source_assets[@]}"; do
  name=$(basename "$path")
  source_record=$(printf '%s' "$source_json" \
    | jq -c --arg name "$name" '.assets[] | select(.name == $name) | [.size, .digest]')
  target_record=$(printf '%s' "$merged_json" \
    | jq -c --arg name "$name" '.assets[] | select(.name == $name) | [.size, .digest]')
  [ "$source_record" = "$target_record" ] || {
    echo "附件校验失败:$name" >&2
    exit 1
  }
done

kind_of() {
  case "$1" in
    *gw-win_*.exe)                    echo "🪟 在线安装器 中国版 (64-bit · exe)";;
    *gw-win-download_*.exe|*gw-overseas12_*.exe) echo "🪟 在线安装器 国际版 (64-bit · exe)";;
    *mumu15*overseas*.exe)            echo "🪟 完整离线安装包 国际版 · 安卓15 (mumu15,默认)";;
    *nemux*overseas*.exe)             echo "🪟 完整离线安装包 国际版 · 安卓12 (nemux)";;
    *nxmain*overseas*.exe)            echo "🪟 完整离线安装包 国际版 · NX主引擎 (nxmain)";;
    MuMu-setup-mumu15-*.exe)          echo "🪟 完整离线安装包 中国版 · 安卓15 (mumu15,默认)";;
    MuMu-setup-nemux-*.exe)           echo "🪟 完整离线安装包 中国版 · 安卓12 (nemux)";;
    MuMu-setup-nxmain-*.exe)          echo "🪟 完整离线安装包 中国版 · NX主引擎 (nxmain)";;
    MuMu-setup-V*.exe|MuMuNG-setup-*.exe) echo "🪟 完整离线安装包 中国版 · 合体版 (64-bit · exe)";;
    *.part.*)                         echo "🧩 分卷片段(需合并)";;
    *)                                echo "安装包";;
  esac
}

{
  echo "## $title"
  echo
  echo "### 下载文件"
  echo
  echo "| 类型 | 文件 | 大小 |"
  echo "|------|------|------|"
  printf '%s' "$merged_json" | jq -r '.assets[] | select(.name != "checksums.sha256") | [.name, .size] | @tsv' \
    | sort | while IFS=$'\t' read -r name size; do
        printf '| %s | `%s` | %d MB |\n' "$(kind_of "$name")" "$name" "$((size / 1048576))"
      done
  echo
  echo "### SHA256 校验"
  echo '```'
  cat "$WORK/merged/checksums.sha256"
  echo '```'
} > "$WORK/notes.md"
gh release edit "$TARGET_TAG" --repo "$REPO" --notes-file "$WORK/notes.md" >/dev/null

gh release delete "$SOURCE_TAG" --repo "$REPO" --yes --cleanup-tag
echo "✅ $SOURCE_TAG 已并入 $TARGET_TAG"
