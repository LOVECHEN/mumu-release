#!/usr/bin/env bash
# MuMu 官方安装包镜像核心逻辑。按【版本】聚合:同一版本的中国版 + 国际版资产放同一个 Release。
# 三类:
#   mac            → tag: mac-<版本>              (macOS 完整 dmg + 完整 tar.gz,两种都能装)
#   win 完整包      → tag: win-<产品版本 V6.x>      (完整离线安装包 ~830MB,免联网直装)
#   win 在线安装器  → tag: win-installer-<下载器版本> (小巧在线下载器 exe)
# 用法: sync.sh <mode>  ,mode ∈ mac-current | win-full | win-installer | mac-backfill
set -uo pipefail
REPO="${GITHUB_REPOSITORY:?need GITHUB_REPOSITORY}"
# 所有官方来源地址不写进公开仓库,统一从仓库 Secret 注入(见 .github/workflows/sync.yml env)。
CDN="${MUMU_CDN:?need MUMU_CDN}"                       # CDN 直链前缀
DL_MAC_CN="${MUMU_DL_MAC_CN:-}"                         # mac 中国版下载端点(完整 URL,含 channel)
DL_MAC_GL="${MUMU_DL_MAC_GL:-}"                         # mac 国际版下载端点
DL_WIN_CN="${MUMU_DL_WIN_CN:-}"                         # win 中国版下载端点(base,后接 ?channel=)
DL_WIN_GL="${MUMU_DL_WIN_GL:-}"                         # win 国际版下载端点
WINFULL_INDEX="${MUMU_WINFULL_INDEX:-}"                 # win 合体版社区索引页
UA="Mozilla/5.0"

# 日志脱敏:GitHub 自动 mask secret 原值,这里再对每个来源地址的【裸主机名】变体补一层
# ::add-mask::(防任何分支/失败路径把不带协议的 host 打进日志)。全脚本(所有 job)共用。
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  for _v in "$CDN" "$DL_MAC_CN" "$DL_MAC_GL" "$DL_WIN_CN" "$DL_WIN_GL" \
            "${MUMU_NX_HOST_GL:-}" "${MUMU_NX_HOST_CN:-}" "$WINFULL_INDEX"; do
    [ -z "$_v" ] && continue
    _h="${_v#http://}"; _h="${_h#https://}"; _h="${_h%%/*}"
    [ -n "$_h" ] && echo "::add-mask::$_h"
  done
fi

head_ok() { curl -fsSI --http1.1 -m 25 "$1" >/dev/null 2>&1; }
redir()   { curl -fsS --http1.1 -m 40 -o /dev/null -w '%{redirect_url}' "$1" 2>/dev/null || true; }
verof()   { printf '%s' "$1" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }

# 资产类型标签(从文件名推断)
kind_of() {
  case "$1" in
    *_default.dmg)                    echo "🍎 全量 中国版 (Apple Silicon · dmg)";;
    *_global.dmg)                     echo "🍎 全量 国际版 (Apple Silicon · dmg)";;
    MuMuPlayerPro-v*-global.dmg)      echo "🍎 全量 国际版 (Apple Silicon · dmg)";;
    MuMuPlayerPro-v*.dmg)             echo "🍎 全量 中国版 (Apple Silicon · dmg)";;
    MuMuUpdater_*_default.tar.gz)      echo "🍎 完整包 中国版 (Apple Silicon · tar.gz)";;
    MuMuMacUpdater_*-global.tar.gz)   echo "🍎 完整包 国际版 (Apple Silicon · tar.gz)";;
    *gw-win_*.exe)                    echo "🪟 在线安装器 中国版 (64-bit · exe)";;
    *gw-win-download_*.exe|*gw-overseas12_*.exe) echo "🪟 在线安装器 国际版 (64-bit · exe)";;
    *mumu15*overseas*.exe)            echo "🪟 完整离线安装包 国际版 · 安卓15 (mumu15,默认)";;
    *nemux*overseas*.exe)             echo "🪟 完整离线安装包 国际版 · 安卓12 (nemux)";;
    *nxmain*overseas*.exe)            echo "🪟 完整离线安装包 国际版 · NX主引擎 (nxmain)";;
    *overseas*.exe)                   echo "🪟 完整离线安装包 国际版 (64-bit · exe)";;
    MuMu-setup-mumu15-*.exe)          echo "🪟 完整离线安装包 中国版 · 安卓15 (mumu15,默认)";;
    MuMu-setup-nemux-*.exe)           echo "🪟 完整离线安装包 中国版 · 安卓12 (nemux)";;
    MuMu-setup-nxmain-*.exe)          echo "🪟 完整离线安装包 中国版 · NX主引擎 (nxmain)";;
    MuMu-setup-V*.exe|MuMuNG-setup-*.exe) echo "🪟 完整离线安装包 中国版 · 合体版 (64-bit · exe)";;
    MuMu-setup-*.exe)                 echo "🪟 完整离线安装包 中国版 (64-bit · exe)";;
    *.part.*)                         echo "🧩 分卷片段(需合并,见下方说明)";;
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

# 文件字节数(macOS/Linux 通用)
_fsize() { stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null || echo 0; }
# ★保险:GitHub Release 单文件硬上限 2 GiB。超此阈值(留安全余量)自动分卷上传,
#   分卷名 <文件>.part.aa/ab/…(GNU/BSD split 同为字母序后缀),下载后合并见 release 说明。
SPLIT_MAX=1992294400   # 1900 MiB

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

  # 3. 下载缺失资产(单文件 > SPLIT_MAX 自动分卷,规避 GitHub 2GiB 上限)
  local DIR; DIR=$(mktemp -d); local NEW=() SPLIT_INFO=() i sz osha parts p2
  for i in "${!W_URL[@]}"; do
    name="${W_NAME[$i]}"
    # 整包名 或 分卷首片(.part.aa)已在 release → 视为已有
    printf '%s\n' "$have" | grep -qxF "$name" && continue
    printf '%s\n' "$have" | grep -qxF "$name.part.aa" && continue
    echo "  📥 $TAG ← $name"
    if ! f=$(_dl "${W_URL[$i]}" "$DIR"); then echo "     ❌ 下载失败"; continue; fi
    sz=$(_fsize "$DIR/$f")
    if [ "$sz" -gt "$SPLIT_MAX" ]; then
      osha=$( cd "$DIR" && sha256sum "$f" | awk '{print $1}' )
      ( cd "$DIR" && split -b "$SPLIT_MAX" "$f" "$f.part." )   # → f.part.aa, f.part.ab …
      rm -f "$DIR/$f"
      parts=$(cd "$DIR" && ls "$f".part.* | wc -l | tr -d ' ')
      for p2 in "$DIR/$f".part.*; do NEW+=("$p2"); done
      SPLIT_INFO+=("$f|$osha|$parts")
      echo "     ✂️ $((sz/1048576))MB > $((SPLIT_MAX/1048576))MB → 分成 $parts 卷上传"
    else
      NEW+=("$DIR/$f"); echo "     ✅ $((sz/1048576)) MB"
    fi
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
    if [ "${#SPLIT_INFO[@]}" -gt 0 ]; then
      echo "### 📦 分卷合并(该文件超 2 GiB 已切片,下齐全部 \`.part.*\` 再合并)"; echo
      local si on os np
      for si in "${SPLIT_INFO[@]}"; do
        on="${si%%|*}"; os=$(printf '%s' "$si" | cut -d'|' -f2); np=$(printf '%s' "$si" | cut -d'|' -f3)
        echo "**\`$on\`**(共 $np 卷:\`$on.part.aa\` … )"
        echo '- Windows(cmd):`copy /b "'"$on"'.part.*" "'"$on"'"`'
        echo '- macOS / Linux:`cat "'"$on"'".part.* > "'"$on"'"`'
        echo "- 合并后整包 SHA256(核对):\`$os\`"; echo
      done
    fi
    echo "---"
    echo "> 🤖 自动镜像于 $(date -u '+%Y-%m-%d %H:%M UTC') · 裸 CDN 直链(网易官方 CDN)。"
    echo "> ⚠️ 仅镜像网易官方**未修改**安装包(原样镜像,未做任何改动)。同一版本的中国版 + 国际版合并在此。"
  } > "$DIR/notes.md"
  gh release edit "$TAG" --repo "$REPO" --notes-file "$DIR/notes.md" >/dev/null
  echo "  ✅ $TAG 就绪(新增 ${#NEW[@]} 个资产)"
  rm -rf "$DIR"
}

mac_specs() { # $1=version  → 打印 mac spec(多命名:新版 MuMuPlayer_ / 老版 MuMuPlayerPro-v / tar.gz)
  local V="$1"
  echo "$CDN/MuMuPlayer_${V}_default.dmg|"
  echo "$CDN/MuMuPlayer_${V}_global.dmg|"
  echo "$CDN/MuMuUpdater_${V}_default.tar.gz|"
  echo "$CDN/MuMuMacUpdater_${V}-global.tar.gz|"
  # 老版本(约 1.4–1.6)官方 CDN 用的命名:MuMuPlayerPro-v<版本>[-global].dmg
  echo "$CDN/MuMuPlayerPro-v${V}.dmg|"
  echo "$CDN/MuMuPlayerPro-v${V}-global.dmg|"
}

do_mac_current() {
  local L V vers=""
  [ -n "$DL_MAC_CN" ] && { L=$(redir "$DL_MAC_CN"); V=$(verof "${L%%\?*}"); [ -n "$V" ] && vers="$vers $V"; }
  [ -n "$DL_MAC_GL" ] && { L=$(redir "$DL_MAC_GL"); V=$(verof "${L%%\?*}"); [ -n "$V" ] && vers="$vers $V"; }
  for V in $(printf '%s\n' $vers | sort -uV); do
    echo "═══ mac-$V ═══"
    mapfile -t S < <(mac_specs "$V")
    ensure_release "mac-$V" "macOS · MuMuPlayer Pro $V" "🍎 macOS 版(MuMuPlayer Pro,Apple Silicon)· 同版本中国版+国际版合并。" "${S[@]}"
  done
}

do_mac_backfill() {
  local V mp p
  for mp in 1.1 1.2 1.3 1.4 1.5 1.6 1.7 1.8 1.9; do for p in $(seq 0 60); do
    V="$mp.$p"
    # 有任何一类存在才处理(HEAD 很轻)
    if head_ok "$CDN/MuMuPlayer_${V}_default.dmg" || head_ok "$CDN/MuMuPlayer_${V}_global.dmg" \
       || head_ok "$CDN/MuMuUpdater_${V}_default.tar.gz" || head_ok "$CDN/MuMuMacUpdater_${V}-global.tar.gz" \
       || head_ok "$CDN/MuMuPlayerPro-v${V}.dmg" || head_ok "$CDN/MuMuPlayerPro-v${V}-global.dmg"; then
      echo "═══ (backfill) mac-$V ═══"
      mapfile -t S < <(mac_specs "$V")
      ensure_release "mac-$V" "macOS · MuMuPlayer Pro $V" "🍎 macOS 版(历史版本)· 同版本中国版+国际版合并。" "${S[@]}"
    fi
  done; done
}

# 在多个渠道里挑版本号最高的直链(网易同一 host 不同渠道版本不一,官网按钮渠道未必最新)。
# 跳过 apinochannel(无效渠道的回退占位)。echo 最高版本的裸 CDN 直链。
best_win() { # base_url  channel...   (base_url 来自 Secret,后接 ?channel=)
  local base="$1"; shift
  [ -z "$base" ] && return 0
  local ch loc bare v
  { for ch in "$@"; do
      loc=$(redir "$base?channel=$ch"); bare="${loc%%\?*}"
      [ -z "$bare" ] && continue
      case "$bare" in *apinochannel*) continue;; esac
      v=$(verof "$bare"); [ -z "$v" ] && continue
      printf '%s\t%s\n' "$v" "$bare"
    done; } | sort -V | tail -1 | cut -f2
}

# win 在线安装器(小巧下载器)→ tag: win-installer-<下载器版本>
do_win_installer() {
  local BCN BGL VCN VGL
  BCN=$(best_win "$DL_WIN_CN" gw-win gwwin);                        VCN=$(verof "$BCN")
  BGL=$(best_win "$DL_WIN_GL" gwwin gw-overseas12 gw-win-download); VGL=$(verof "$BGL")
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
  [ -z "$WINFULL_INDEX" ] && { echo "⏭ 未配置 MUMU_WINFULL_INDEX,跳过 win-full"; return 0; }
  HTML=$(curl -fsSL --http1.1 -m 40 -A "$UA" "$WINFULL_INDEX" 2>/dev/null || true)
  [ -z "$HTML" ] && { echo "❌ 离线包索引拉取失败,跳过"; return 0; }
  URL=$(printf '%s' "$HTML" | grep -oE "https?://[A-Za-z0-9.-]+/MuMu-setup-V[0-9.]+-[0-9]+\.exe" | head -1)
  [ -z "$URL" ] && { echo "❌ 未解析到离线包,跳过"; return 0; }
  PVER=$(printf '%s' "$HTML" | grep -oE 'V[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  [ -z "$PVER" ] && PVER="V$(verof "$URL")"
  echo "═══ win-$PVER(完整离线安装包)═══"
  ensure_release "win-$PVER" "Windows 完整安装包 · MuMu模拟器12 $PVER" \
    "🪟 Windows 完整离线安装包(~830MB,免联网直装,即产品 $PVER)。国际版见 win-global-offline-*。" \
    "$URL|"
}

# Windows 国际版完整离线安装包(三引擎:mumu15=安卓15/nemux=安卓12/nxmain=NX主)。
# URL 全自动发现:scripts/nx_discover.py 调用官方下载接口 /api/v2/download/nx,
#   拿到 data.components[].link(每引擎完整离线 setup exe)。接口不可用(网络等)时回退内置直链,
#   保证 Release 不丢。命名 = MuMu-setup-<引擎>-V<版本>-overseas-<时间戳>.exe。
WGO_FALLBACK_VER="6.8.0"
WGO_FALLBACK=(
  "$CDN/MuMu-setup-mumu15-V15.8.0.5677-overseas-0923052014.exe"
  "$CDN/MuMu-setup-nemux-V12.8.0.5676-overseas-0923051918.exe"
  "$CDN/MuMu-setup-nxmain-V1.8.0.5675-overseas-0923051933.exe"
)
do_win_global_offline() {
  local OUT VER="" URLS=() line
  OUT=$(python3 "$(dirname "$0")/nx_discover.py" 2>/dev/null) || OUT=""
  while IFS= read -r line; do
    case "$line" in
      VERSION=*)  VER="${line#VERSION=}";;
      https://*)  URLS+=("$line");;
    esac
  done <<< "$OUT"
  if [ "${#URLS[@]}" -eq 0 ]; then
    echo "  ⚠ nx 自动发现失败,回退内置直链(v$WGO_FALLBACK_VER)"
    URLS=("${WGO_FALLBACK[@]}"); VER="$WGO_FALLBACK_VER"
  fi
  local TAGVER; TAGVER=$(printf '%s' "$VER" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  [ -z "$TAGVER" ] && TAGVER="$WGO_FALLBACK_VER"
  echo "═══ win-global-offline-$TAGVER(nx 发现 ${#URLS[@]} 引擎)═══"
  local specs=() u; for u in "${URLS[@]}"; do specs+=("$u|"); done
  ensure_release "win-global-offline-$TAGVER" "Windows 国际版完整安装包 · MuMu Player 12 (安卓15/12) $TAGVER" \
    "🪟 Windows 国际版完整离线安装包(免联网直装)· 三引擎:**mumu15(安卓15,默认)** / nemux(安卓12)/ nxmain(NX主)。URL 由官方下载接口自动发现(scripts/nx_discover.py)。" \
    "${specs[@]}"
}

# Windows 国内版完整离线安装包(三引擎,官方下载接口)。同 Global,地区参数不同(usage=0/language=zh-Hans/无 overseas)。
# ★实测 GitHub runner 可正常发现+下载;国内版往往比国际版新(实测 CN 6.8.2 vs Global 6.8.0)。
#   接口不可用(凭据缺失/网络异常)时跳过(CN 合体版仍由 win-full 社区索引覆盖,不受影响)。
do_win_cn_offline() {
  local OUT VER="" URLS=() line
  OUT=$(python3 "$(dirname "$0")/nx_discover.py" cn 2>/dev/null) || OUT=""
  while IFS= read -r line; do
    case "$line" in
      VERSION=*)  VER="${line#VERSION=}";;
      https://*)  URLS+=("$line");;
    esac
  done <<< "$OUT"
  if [ "${#URLS[@]}" -eq 0 ]; then
    echo "  ⏭ CN nx 未发现(密钥缺失/网络异常),跳过 —— CN 合体版仍由 win-full 覆盖"
    return 0
  fi
  local TAGVER; TAGVER=$(printf '%s' "$VER" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  echo "═══ win-cn-offline-$TAGVER(nx 发现 ${#URLS[@]} 引擎)═══"
  local specs=() u; for u in "${URLS[@]}"; do specs+=("$u|"); done
  ensure_release "win-cn-offline-$TAGVER" "Windows 国内版完整安装包 · MuMu模拟器12 (安卓15/12) $TAGVER" \
    "🪟 Windows 国内版完整离线安装包(免联网直装)· 三引擎:**mumu15(安卓15,默认)** / nemux(安卓12)/ nxmain(NX主)。URL 由官方下载接口自动发现(scripts/nx_discover.py)。合体版见 win-*。" \
    "${specs[@]}"
}

case "${1:-}" in
  mac-current)        do_mac_current;;
  mac-backfill)       do_mac_backfill;;
  win-installer)      do_win_installer;;
  win-full)           do_win_full;;
  win-global-offline) do_win_global_offline;;
  win-cn-offline)     do_win_cn_offline;;
  *) echo "usage: sync.sh mac-current|win-installer|win-full|win-global-offline|win-cn-offline|mac-backfill" >&2; exit 2;;
esac
