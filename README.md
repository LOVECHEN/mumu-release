<div align="center">

# 📦 MuMu 官方安装包镜像

**MuMu 模拟器 / MuMuPlayer Pro 官方安装包 —— 每日自动跟随官方,直发 GitHub Release**

macOS(Apple Silicon · dmg + 增量 tar.gz)· Windows(64-bit · exe)· 中国版 + 国际版

[![最新](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?label=最新发布&color=2f7d32)](https://github.com/LOVECHEN/mumu-release/releases/latest)
[![最近更新](https://img.shields.io/github/release-date/LOVECHEN/mumu-release?label=最近更新&color=4c8bf5)](https://github.com/LOVECHEN/mumu-release/releases)
[![自动同步](https://github.com/LOVECHEN/mumu-release/actions/workflows/sync.yml/badge.svg)](https://github.com/LOVECHEN/mumu-release/actions/workflows/sync.yml)

[**⬇️ 打开最新发布**](https://github.com/LOVECHEN/mumu-release/releases/latest) · [📦 全部版本](https://github.com/LOVECHEN/mumu-release/releases)

</div>

---

## ⬇️ 下载矩阵(三类 · 同版本中国版+国际版合并在一个 Release)

进入对应 Release 页,下载官方**原始安装包**(文件名自带版本号,附 `checksums.sha256` 可校验):

| 类型 | tag | 内容 | 页面 |
|------|-----|------|------|
| 🍎 **macOS** | `mac-<版本>` | MuMuPlayer Pro 全量 `dmg`(Apple Silicon)+ 增量 `tar.gz`,**中国版+国际版同版本并在一起** | [![mac](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=mac-*&label=版本&color=2f7d32)](https://github.com/LOVECHEN/mumu-release/releases?q=mac) |
| 🪟 **Windows 完整包** | `win-<产品版本>` | **完整离线安装包** `exe`(~830 MB,免联网双击直装)· 主 Windows 下载 | [![win](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-V*&label=产品版本&color=c0392b)](https://github.com/LOVECHEN/mumu-release/releases?q=win-V) |
| 🪟 **Windows 在线安装器** | `win-installer-<下载器版本>` | 官方小巧在线下载器 `exe`(~5–6 MB,运行后再联网拉完整包) | [![installer](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-installer-*&label=下载器&color=4c8bf5)](https://github.com/LOVECHEN/mumu-release/releases?q=win-installer) |

> - **同一版本的中国版 + 国际版资产放在同一个 Release 里**(文件名自带 `default`/`global` 区分,不冲突)。
> - **macOS = MuMuPlayer Pro**(`1.9.x`);Windows 网络不好优先下 **完整包**(双击即装),在线安装器是小下载器。
> - 资产**保留官方原名**,例:`MuMuPlayer_1.9.2_default.dmg` + `MuMuPlayer_1.9.2_global.dmg` 同处一个 `mac-1.9.2`。
> - 仓库 **Latest** = macOS 最新版本。历史版本累积不删。

> **⚠️ Windows 三个版本号别混**(同一个 MuMu模拟器12,不同组件各自编号):
> - **产品 / 模拟器版本 `V6.x`**(如 V6.2.5)—— 官网/软件显示的版本,**完整包** `win-V6.x` 用它。
> - **在线安装器"下载器"版本 `6.0.x`** —— 小下载器自己的号,`win-installer-6.0.x` 用它。
> - **完整包内部构建号 `V5.30.x`** —— 只在离线包**文件名**里,装出来即产品 `V6.x`。

---

## 🔄 工作原理

[`.github/workflows/sync.yml`](.github/workflows/sync.yml) 每天 **06:00 UTC(北京 14:00)** 运行,核心逻辑在 [`scripts/sync.sh`](scripts/sync.sh),**按版本聚合、幂等**(CDN 上有、Release 里没有的资产会补进去,已完整则跳过):

- **`mac` 任务**:官方 api 解析中国版 + 国际版当前 mac 版本,每个版本聚合 4 类直链(dmg / tar.gz × CN / Global)中存在的,发布/补齐 `mac-<版本>`。
- **`win` 任务**:从社区索引取最新**完整离线安装包**直链 + 产品版本,发 `win-<V6.x>`(~830 MB)。官方无干净端点,索引失败自动跳过(唯一第三方依赖)。
- **`win-installer` 任务**:官方 api 解析中国版 + 国际版当前在线安装器版本,发 `win-installer-<下载器版本>`;两边同版本则合并同一 Release。
- **`backfill-mac`(一次性,手动 `backfill=yes`)**:遍历候选版本号 `HEAD` 探测,把网易 CDN 上**还活着的历史 mac 包**补成 `mac-<版本>`(同版本 CN+Global 合并)。网易老版本保留不规律,能补到哪算哪。

也可在 **Actions → Sync MuMu → Run workflow** 手动触发(`only` = mac/win/installer/all)。

---

## ⚖️ 声明

本仓库仅镜像网易 MuMu **官方公开分发**的安装包,不含任何破解 / 授权绕过 / 二进制修改。
版权归网易(NetEase)所有,请遵守 MuMu 官方用户协议。官方站点:
[mumu.163.com](https://mumu.163.com)(中国版)· [mumuplayer.com](https://www.mumuplayer.com)(国际版)。
