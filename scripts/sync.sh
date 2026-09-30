#!/usr/bin/env bash
# MuMu 官方安装包镜像核心逻辑。按【版本】聚合:同一版本的中国版 + 国际版资产放同一个 Release。
# 三类:
#   mac            → tag: mac-<版本>              (macOS dmg + 增量 tar.gz)
#   win 完整包      → tag: win-<产品版本 V6.x>      (完整离线安装包 ~830MB,免联网直装)
#   win 在线安装器  → tag: win-installer-<下载器版本> (小巧在线下载器 exe)
# 用法: sync.sh <mode>  ,mode ∈ mac-current | win-full | win-installer | mac-backfill
set -uo pipefail
REPO="${GITHUB_REPOSITORY:?need GITHUB_REPOSITORY}"
CDN="https://a11.gdl.netease.com"
UA="Mozilla/5.0"

head_ok() { curl -fsSI --http1.1 -m 25 "$1" >/dev/null 2>&1; }
redir()   { curl -fsS --http1.1 -m 40 -o /dev/null -w '%{redirect_url}' "$1" 2>/dev/null || true; }
verof()   { printf '%s' "$1" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }

# 资产类型标签(从文件名推断)
kind_of() {
  case "$1" in
    *_default.dmg)                    echo "🍎 全量 中国版 (Apple Silicon · dmg)";;
    *_global.dmg)                     echo "🍎 全量 国际版 (Apple Silicon · dmg)";;
    MuMuUpdater_*_default.tar.gz)      echo "🍎 增量热更 中国版 (updater · tar.gz)";;
    MuMuMacUpdater_*-global.tar.gz)   echo "🍎 增量热更 国际版 (updater · tar.gz)";;
    *gw-win_*.exe)                    echo "🪟 在线安装器 中国版 (64-bit · exe)";;
    *gw-win-download_*.exe|*gw-overseas12_*.exe) echo "🪟 在线安装器 国际版 (64-bit · exe)";;
    *overseas*.exe)                   echo "🪟 完整离线安装包 国际版 (64-bit · exe)";;
    MuMu-setup-*.exe|MuMuNG-setup-*.exe) echo "🪟 完整离线安装包 中国版 (64-bit · exe)";;
    *) echo "安装包";;
  esac
}

# 下载 url 到 dir,成功打印文件名
_dl() {
  local url="$1" dir="$2" f="${1##*/}"; f="${f%%\?*}"
  if curl -fL --http1.1 --retry 5 --retry-delay 6 --retry-all-errors --retry-connrefused --connect-timeout 40 -o "$dir/$f" "$url" 2>/dev/null; then
    echo "$f"; return 0
  fi
  rm -f "$dir/$f"; return 1
}

# ensure_release TAG TITLE INTRO  spec...   spec = "url|kind(留空则推断)"
# 幂等:把 CDN 上存在、但 Release 里还没有的资产补进去(合并 CN+Global),已完整则跳过。
ensure_release() {
  local TAG="$1" TITLE="$2" INTRO="$3"; shift 3
  local specs=("$@") s url name
  # 1. 过滤出 CDN 上真实存在的资产
  local W_URL=() W_NAME=()
  for s in "${specs[@]}"; do
    url="${s%%|*}"; name="${url##*/}"; name="${name%%\?*}"
    [ -z "$url" ] && continue
    if head_ok "$url"; then W_URL+=("$url"); W_NAME+=("$name"); fi
  done
  [ "${#W_URL[@]}" -eq 0 ] && { echo "  ⏭ $TAG: CDN 无资产,跳过"; return 0; }

  # 2. 已有 Release 的资产名
  local exists=false have=""
  if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    exists=true
    have=$(gh release view "$TAG" --repo "$REPO" --json assets --jq '.assets[].name' 2>/dev/null)
  fi

  # 3. 下载缺失资产
  local DIR; DIR=$(mktemp -d); local NEW=() i
  for i in "${!W_URL[@]}"; do
    name="${W_NAME[$i]}"
    printf '%s\n' "$have" | grep -qxF "$name" && continue
    echo "  📥 $TAG ← $name"
    if f=$(_dl "${W_URL[$i]}" "$DIR"); then
      NEW+=("$DIR/$f"); echo "     ✅ $(( $(stat -c%s "$DIR/$f") / 1048576 )) MB"
    else echo "     ❌ 下载失败"; fi
  done
  if [ "${#NEW[@]}" -eq 0 ]; then echo "  ⏭ $TAG: 已完整,跳过"; rm -rf "$DIR"; return 0; fi

  # 4. checksums:老的下回来 + 追加新文件的 sha256
  local CK="$DIR/checksums.sha256"; : > "$CK"
  if $exists && printf '%s\n' "$have" | grep -qxF "checksums.sha256"; then
    gh release download "$TAG" --repo "$REPO" --pattern 'checksums.sha256' --dir "$DIR" --clobber 2>/dev/null || : > "$CK"
  fi
  ( cd "$DIR" && for p in "${NEW[@]}"; do sha256sum "$(basename "$p")"; done ) >> "$CK"

  # 5. 上传(新建 or 追加)
  if $exists; then
    gh release upload "$TAG" --repo "$REPO" --clobber "${NEW[@]}" "$CK"
  else
    gh release create "$TAG" --repo "$REPO" --title "$TITLE" --notes "(生成中…)" --latest=false "${NEW[@]}" "$CK"
  fi

  # 6. 用最终资产列表重建说明
  {
    echo "## $TITLE"; echo
    [ -n "$INTRO" ] && { echo "$INTRO"; echo; }
    echo "### 下载文件"; echo
    echo "| 类型 | 文件 | 大小 |"; echo "|------|------|------|"
    gh release view "$TAG" --repo "$REPO" --json assets --jq '.assets[] | "\(.name)\t\(.size)"' \
      | while IFS=$'\t' read -r n sz; do
          [ "$n" = "checksums.sha256" ] && continue
          printf '| %s | `%s` | %d MB |\n' "$(kind_of "$n")" "$n" "$((sz/1048576))"
        done
    echo; echo "### SHA256 校验"; echo '```'; cat "$CK"; echo '```'; echo
    echo "---"
    echo "> 🤖 自动镜像于 $(date -u '+%Y-%m-%d %H:%M UTC') · 裸 CDN 直链(a11.gdl.netease.com)。"
    echo "> ⚠️ 仅镜像网易官方**未修改**安装包,不含任何破解 / 授权绕过。同一版本的中国版 + 国际版合并在此。"
  } > "$DIR/notes.md"
  gh release edit "$TAG" --repo "$REPO" --notes-file "$DIR/notes.md" >/dev/null
  echo "  ✅ $TAG 就绪(新增 ${#NEW[@]} 个资产)"
  rm -rf "$DIR"
}

mac_specs() { # $1=version  → 打印 4 条 mac spec
  local V="$1"
  echo "$CDN/MuMuPlayer_${V}_default.dmg|"
  echo "$CDN/MuMuPlayer_${V}_global.dmg|"
  echo "$CDN/MuMuUpdater_${V}_default.tar.gz|"
  echo "$CDN/MuMuMacUpdater_${V}-global.tar.gz|"
}

do_mac_current() {
  local L V vers=""
  L=$(redir "https://mumu.nie.netease.com/api/dl/mac?channel=gw-mac");        V=$(verof "${L%%\?*}"); [ -n "$V" ] && vers="$vers $V"
  L=$(redir "https://api.mumuplayer.com/api/dl/mac?channel=gw-mac-download"); V=$(verof "${L%%\?*}"); [ -n "$V" ] && vers="$vers $V"
  for V in $(printf '%s\n' $vers | sort -uV); do
    echo "═══ mac-$V ═══"
    mapfile -t S < <(mac_specs "$V")
    ensure_release "mac-$V" "macOS · MuMuPlayer Pro $V" "🍎 macOS 版(MuMuPlayer Pro,Apple Silicon)· 同版本中国版+国际版合并。" "${S[@]}"
  done
}

do_mac_backfill() {
  local V mp p
  for mp in 1.6 1.7 1.8 1.9; do for p in $(seq 0 45); do
    V="$mp.$p"
    # 有任何一类存在才处理(HEAD 很轻)
    if head_ok "$CDN/MuMuPlayer_${V}_default.dmg" || head_ok "$CDN/MuMuPlayer_${V}_global.dmg" \
       || head_ok "$CDN/MuMuUpdater_${V}_default.tar.gz" || head_ok "$CDN/MuMuMacUpdater_${V}-global.tar.gz"; then
      echo "═══ (backfill) mac-$V ═══"
      mapfile -t S < <(mac_specs "$V")
      ensure_release "mac-$V" "macOS · MuMuPlayer Pro $V" "🍎 macOS 版(历史版本)· 同版本中国版+国际版合并。" "${S[@]}"
    fi
  done; done
}

# 在多个渠道里挑版本号最高的直链(网易同一 host 不同渠道版本不一,官网按钮渠道未必最新)。
# 跳过 apinochannel(无效渠道的回退占位)。echo 最高版本的裸 CDN 直链。
best_win() { # host  channel...
  local host="$1"; shift
  local ch loc bare v
  { for ch in "$@"; do
      loc=$(redir "https://$host/api/dl/win?channel=$ch"); bare="${loc%%\?*}"
      [ -z "$bare" ] && continue
      case "$bare" in *apinochannel*) continue;; esac
      v=$(verof "$bare"); [ -z "$v" ] && continue
      printf '%s\t%s\n' "$v" "$bare"
    done; } | sort -V | tail -1 | cut -f2
}

# win 在线安装器(小巧下载器)→ tag: win-installer-<下载器版本>
do_win_installer() {
  local BCN BGL VCN VGL
  BCN=$(best_win "mumu.nie.netease.com" gw-win gwwin);                        VCN=$(verof "$BCN")
  BGL=$(best_win "api.mumuplayer.com"   gwwin gw-overseas12 gw-win-download); VGL=$(verof "$BGL")
  local INTRO="🪟 Windows 在线安装器(官方下载按钮给的小巧下载器,运行后再联网拉完整包)· 同版本中国版+国际版合并。要免联网直装请下【完整离线安装包】。"
  if [ -n "$VCN" ] && [ "$VCN" = "$VGL" ]; then
    echo "═══ win-installer-$VCN (CN+GL 同版本) ═══"
    ensure_release "win-installer-$VCN" "Windows 在线安装器 · MuMu模拟器12 v$VCN" "$INTRO" "$BCN|" "$BGL|"
  else
    [ -n "$VCN" ] && { echo "═══ win-installer-$VCN (CN) ═══"; ensure_release "win-installer-$VCN" "Windows 在线安装器 · MuMu模拟器12 v$VCN" "$INTRO" "$BCN|"; }
    [ -n "$VGL" ] && { echo "═══ win-installer-$VGL (GL) ═══"; ensure_release "win-installer-$VGL" "Windows 在线安装器 · MuMu Player 12 v$VGL" "$INTRO" "$BGL|"; }
  fi
}

# win 完整离线安装包(主 Windows 下载)→ tag: win-<产品版本>
do_win_full() {
  local HTML URL PVER
  HTML=$(curl -fsSL --http1.1 -m 40 -A "$UA" "https://www.cnblogs.com/wutou/p/19476571" 2>/dev/null || true)
  [ -z "$HTML" ] && { echo "❌ 离线包索引拉取失败,跳过"; return 0; }
  URL=$(printf '%s' "$HTML" | grep -oE "https://a11\.gdl\.netease\.com/MuMu-setup-V[0-9.]+-[0-9]+\.exe" | head -1)
  [ -z "$URL" ] && { echo "❌ 未解析到离线包,跳过"; return 0; }
  PVER=$(printf '%s' "$HTML" | grep -oE 'V[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  [ -z "$PVER" ] && PVER="V$(verof "$URL")"
  echo "═══ win-$PVER(完整离线安装包)═══"
  ensure_release "win-$PVER" "Windows 完整安装包 · MuMu模拟器12 $PVER" \
    "🪟 Windows 完整离线安装包(~830MB,免联网直装,即产品 $PVER)。文件名内部构建号 V5.30.x,装出来即 $PVER。国际版离线包暂无可靠源,补到即并入。" \
    "$URL|"
}

case "${1:-}" in
  mac-current)   do_mac_current;;
  mac-backfill)  do_mac_backfill;;
  win-installer) do_win_installer;;
  win-full)      do_win_full;;
  *) echo "usage: sync.sh mac-current|win-installer|win-full|mac-backfill" >&2; exit 2;;
esac
