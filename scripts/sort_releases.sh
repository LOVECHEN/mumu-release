#!/usr/bin/env bash
# GitHub 的 Releases 页面只能按 tag 所在提交的时间排序。本脚本把这个时间映射为:
#   1. Release 内最新原始文件的 CDN Last-Modified(源文件时间),倒序;
#   2. 上述时间完全相同时,按 tag 中的语义版本号倒序(sort -V)。
# 手动补档的 GitHub 上传时间不参与排序。源文件日后被 CDN 删除时,优先复用 tag 标记中已保存的源时间;
# 从未取到过源时间的条目统一沉到历史区底部,再按版本号排序。为保证 GitHub 排序键唯一,
# 同秒条目会按上述次序依次减 1 秒。标记提交不进入 main,不改仓库文件,不重建 Release,
# 也不会丢失附件或下载计数。
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

DATA=""
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

  DATA+="${source_epoch}"$'\t'"${version}"$'\t'"${tag}"$'\n'
done <<< "$RELEASES"

DATA=$(printf '%s' "$DATA" | sed '/^$/d' \
  | sort -t $'\t' -k1,1nr -k2,2Vr -k3,3r)

[ -n "$DATA" ] || { echo "⏭ 无 release,跳过"; exit 0; }

parent=$(git rev-parse origin/main)
previous_epoch=""
newest_tag=""
changed=0

while IFS=$'\t' read -r source_epoch version tag; do
  [ -z "$newest_tag" ] && newest_tag="$tag"
  # 2000-01-01 仅是“源时间已不可取”的历史区排序基准,不冒充真实文件时间。
  if [ "$source_epoch" -eq 0 ]; then marker_epoch=946684800; else marker_epoch="$source_epoch"; fi
  if [ -n "$previous_epoch" ] && [ "$marker_epoch" -ge "$previous_epoch" ]; then
    marker_epoch=$((previous_epoch - 1))
  fi
  previous_epoch="$marker_epoch"

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

gh release edit "$newest_tag" --repo "$REPO" --latest >/dev/null
echo "✅ Release 排序完成:更新 $changed 个 tag; Latest=$newest_tag"
