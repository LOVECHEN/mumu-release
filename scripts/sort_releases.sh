#!/usr/bin/env bash
# GitHub Releases 页面按 tag 所在提交的日期排序,同一天内仍可能沿用 Release 的内部创建顺序。
# 本脚本把排序日期映射为:
#   1. Release 内最新原始文件的 CDN Last-Modified(源文件时间),倒序;
#   2. 上述时间完全相同时,按 tag 中的语义版本号倒序(sort -V)。
# 手动补档的 GitHub 上传时间不参与排序。源文件日后被 CDN 删除时,优先复用 tag 标记中已保存的源时间;
# 从未取到过源时间的旧条目插回同系列相邻版本之间,再按版本号排序。为保证 GitHub 排序键唯一,
# 相邻条目会保证使用不同的 UTC 日期。标记提交不进入 main,不改仓库文件。若既有 Release
# 的内部旧顺序仍与目标不符,只重建错位项;正文和附件内容不变,该项下载计数会重新开始。
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?need GITHUB_REPOSITORY}"
CDN="${MUMU_CDN:?need MUMU_CDN}"
CDN="${CDN%/}"

git fetch --force --tags origin

RELEASES=$(gh api --paginate "repos/$REPO/releases?per_page=100" \
  --jq '.[]
    | select(.draft == false and .prerelease == false)
    | [.tag_name, ([.assets[].name | select(. != "checksums.sha256")] | unique | join("|"))]
    | @tsv')

RAW_DATA=""
while IFS=$'\t' read -r tag names; do
  [ -z "$tag" ] && continue
  version=$(printf '%s' "$tag" | grep -oE '[0-9]+(\.[0-9]+)+' | head -1 || true)
  version="${version:-0}"
  source_epoch=0

  IFS='|' read -ra assets <<< "$names"
  for name in "${assets[@]}"; do
    # 分卷是 GitHub 上传形式;CDN 上的源文件仍是未分卷的原名。
    source_name=$(printf '%s' "$name" | sed -E 's/\.part\.[a-z][a-z]$//')
    headers=$(curl -fsSI --http1.1 -m 25 "$CDN/$source_name" 2>/dev/null || true)
    modified=$(printf '%s\n' "$headers" \
      | sed -n 's/^[Ll]ast-[Mm]odified:[[:space:]]*//p' | tr -d '\r' | tail -1)
    [ -z "$modified" ] && continue
    epoch=$(date -u -d "$modified" +%s)
    [ "$epoch" -gt "$source_epoch" ] && source_epoch="$epoch"
  done

  # CDN 文件被删除后,从上次标记提交恢复已验证的源时间。
  if [ "$source_epoch" -eq 0 ]; then
    saved=$(git show -s --format=%B "$tag^{commit}" \
      | sed -n 's/^source-last-modified: \([0-9][0-9]*\)$/\1/p' | tail -1)
    [ -n "$saved" ] && source_epoch="$saved"
  fi

  RAW_DATA+="${source_epoch}"$'\t'"${version}"$'\t'"${tag}"$'\n'
done <<< "$RELEASES"

# 这 5 个早期文件已从 CDN 下线且没有历史源时间可恢复。将它们紧跟在同系列
# 已知的上一版 mac-1.4.32 后,再按语义版本倒序插回,而不使用补档上传时间。
legacy_anchor=$(printf '%s' "$RAW_DATA" \
  | awk -F $'\t' '$3 == "mac-1.4.32" { print $1; exit }')
legacy_anchor="${legacy_anchor:-946684800}"
legacy_rank=0
DATA=""
while IFS=$'\t' read -r source_epoch version tag; do
  [ -z "$tag" ] && continue
  sort_epoch="$source_epoch"
  if [ "$source_epoch" -eq 0 ]; then
    case "$tag" in
      mac-1.4.22|mac-1.4.18|mac-1.4.11|mac-1.4.10|mac-1.4.5)
        legacy_rank=$((legacy_rank + 1))
        sort_epoch=$((legacy_anchor - legacy_rank))
        ;;
      *) sort_epoch=946684800;;
    esac
  fi
  DATA+="${sort_epoch}"$'\t'"${source_epoch}"$'\t'"${version}"$'\t'"${tag}"$'\n'
done <<< "$(printf '%s' "$RAW_DATA" | sed '/^$/d' | sort -t $'\t' -k2,2Vr -k3,3r)"

DATA=$(printf '%s' "$DATA" | sed '/^$/d' \
  | sort -t $'\t' -k1,1nr -k3,3Vr -k4,4r)

[ -n "$DATA" ] || { echo "⏭ 无 release,跳过"; exit 0; }

parent=$(git rev-parse origin/main)
previous_epoch=""
previous_day=""
newest_tag=""
changed=0

while IFS=$'\t' read -r sort_epoch source_epoch version tag; do
  [ -z "$newest_tag" ] && newest_tag="$tag"
  marker_epoch="$sort_epoch"
  marker_day=$(date -u -d "@$marker_epoch" +%F)
  if [ -n "$previous_day" ] && [[ "$marker_day" > "$previous_day" || "$marker_day" = "$previous_day" ]]; then
    marker_epoch=$((previous_epoch - 86400))
    marker_day=$(date -u -d "@$marker_epoch" +%F)
  fi
  previous_epoch="$marker_epoch"
  previous_day="$marker_day"

  current=$(git rev-parse "$tag^{commit}")
  current_epoch=$(git show -s --format=%ct "$current")
  current_source=$(git show -s --format=%B "$current" \
    | sed -n 's/^source-last-modified: \([0-9][0-9]*\)$/\1/p' | tail -1)
  if [ "$current_epoch" -eq "$marker_epoch" ] && [ "$current_source" = "$source_epoch" ]; then
    printf '✓ %-32s source=%s version=%s\n' "$tag" "$source_epoch" "$version"
    continue
  fi

  tree=$(git rev-parse "$tag^{tree}")
  marker=$(
    printf 'release-order: %s\nsource-last-modified: %s\n' "$tag" "$source_epoch" |
      GIT_AUTHOR_NAME='github-actions[bot]' \
      GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
      GIT_AUTHOR_DATE="@$marker_epoch +0000" \
      GIT_COMMITTER_NAME='github-actions[bot]' \
      GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
      GIT_COMMITTER_DATE="@$marker_epoch +0000" \
      git commit-tree "$tree" -p "$parent"
  )
  git tag -f "$tag" "$marker" >/dev/null
  git push --force origin "refs/tags/$tag" >/dev/null
  changed=$((changed + 1))
  printf '↑ %-32s source=%s version=%s\n' "$tag" "$source_epoch" "$version"
done <<< "$DATA"

# REST 列表和网页使用 Release 创建时固化的日期索引。旧 tag 改时间后索引不会刷新,
# 因此只重建排在首个错误位置的条目,直到网页顺序与目标一致。
rebuild_release() {
  local tag="$1" dir title prerelease before after
  dir=$(mktemp -d)
  mkdir "$dir/assets"
  gh api "repos/$REPO/releases/tags/$tag" --jq '.body' > "$dir/notes.md"
  title=$(gh api "repos/$REPO/releases/tags/$tag" --jq '.name')
  prerelease=$(gh api "repos/$REPO/releases/tags/$tag" --jq '.prerelease')
  before=$(gh api "repos/$REPO/releases/tags/$tag" \
    --jq '[.assets[] | [.name, .size, .digest]] | sort')

  gh release download "$tag" --repo "$REPO" --dir "$dir/assets"
  gh release delete "$tag" --repo "$REPO" --yes
  local args=(gh release create "$tag" --repo "$REPO" --verify-tag \
    --title "$title" --notes-file "$dir/notes.md" --latest=false)
  [ "$prerelease" = true ] && args+=(--prerelease)
  args+=("$dir"/assets/*)
  "${args[@]}" >/dev/null

  after=$(gh api "repos/$REPO/releases/tags/$tag" \
    --jq '[.assets[] | [.name, .size, .digest]] | sort')
  if [ "$before" != "$after" ]; then
    echo "❌ $tag 重建后的附件清单不一致" >&2
    return 1
  fi
  rm -rf "$dir"
  printf '↻ %-32s 刷新网页排序索引\n' "$tag"
}

target_order=$(printf '%s\n' "$DATA" | cut -f4)
rebuilt=0
max_rebuilds=$(printf '%s\n' "$target_order" | sed '/^$/d' | wc -l)
while :; do
  actual_order=$(gh api --paginate "repos/$REPO/releases?per_page=100" \
    --jq '.[] | select(.draft == false and .prerelease == false) | .tag_name')
  [ "$actual_order" = "$target_order" ] && break

  mismatch=$(paste <(printf '%s\n' "$target_order") <(printf '%s\n' "$actual_order") \
    | awk '$1 != $2 { print $2; exit }')
  if [ -z "$mismatch" ] || [ "$rebuilt" -ge "$max_rebuilds" ]; then
    echo "❌ 无法收敛 GitHub Releases 网页顺序" >&2
    exit 1
  fi
  rebuild_release "$mismatch"
  rebuilt=$((rebuilt + 1))
done

gh release edit "$newest_tag" --repo "$REPO" --latest >/dev/null
echo "✅ Release 排序完成:更新 $changed 个 tag,重建 $rebuilt 个错位项; Latest=$newest_tag"
