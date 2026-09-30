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

## ⬇️ 下载矩阵

进入对应 Release 页,下载官方**原始安装包**(文件名自带版本号,附 `checksums.sha256` 可校验):

| 平台 | 渠道 | 内容 | 页面 |
|------|------|------|------|
| 🍎 **macOS** | 中国版 | 全量 `dmg` + 增量 `tar.gz`(Apple Silicon) | [![mac-cn](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=mac-cn-*&label=版本&color=2f7d32)](https://github.com/LOVECHEN/mumu-release/releases?q=mac-cn) |
| 🍎 **macOS** | 国际版 | 全量 `dmg`(Apple Silicon) | [![mac-global](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=mac-global-*&label=版本&color=b58900)](https://github.com/LOVECHEN/mumu-release/releases?q=mac-global) |
| 🪟 **Windows** | 中国版 | **完整离线安装包** `exe`(~830 MB,免联网直装) | [![win-cn-offline](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-cn-offline-*&label=产品版本&color=c0392b)](https://github.com/LOVECHEN/mumu-release/releases?q=win-cn-offline) |
| 🪟 **Windows** | 中国版 | 在线安装器 `exe`(~6 MB,运行后再拉) | [![win-cn](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-cn-6*&label=下载器&color=4c8bf5)](https://github.com/LOVECHEN/mumu-release/releases?q=win-cn-6) |
| 🪟 **Windows** | 国际版 | 在线安装器 `exe`(~5 MB) | [![win-global](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-global-*&label=下载器&color=6f42c1)](https://github.com/LOVECHEN/mumu-release/releases?q=win-global) |

> - **macOS = MuMuPlayer Pro**(版本号 `1.9.x`,Apple Silicon 原生 dmg;中国版另附增量热更 `tar.gz`)。
> - **Windows = MuMu 模拟器 12**。网络不好优先下 **完整离线安装包**(~830 MB,双击即装);在线安装器是官方小巧下载器(exe ~5–6 MB,运行后再联网拉完整包)。
> - 资产**保留官方原名**,例:mac `MuMuPlayer_1.9.6_default.dmg`、win 离线 `MuMu-setup-V5.30.1.3586-*.exe`、win 在线 `MuMu_6.0.3_gw-win_zh-Hans_*.exe`。
> - 每个版本一个独立 Release,历史累积**永不删除**。仓库 **Latest** = macOS 中国版最新。

> **⚠️ Windows 三个版本号别混**(同一个 MuMu模拟器12,不同组件各自编号):
> - **产品 / 模拟器版本 `V6.x`**(如 V6.2.5)—— 官网和软件里显示的版本,**完整离线安装包**标题用它。
> - **在线安装器"下载器"版本 `6.0.x`** —— 那个 6 MB 小下载器自己的号(≠ 产品版本)。
> - **离线安装包内部构建号 `V5.30.x`** —— 离线包**文件名**里的号,装出来即产品 `V6.x`。

---

## 🔄 工作原理

[`.github/workflows/sync.yml`](.github/workflows/sync.yml) 每天 **06:00 UTC(北京 14:00)** 运行:

**`mirror` 任务**(mac dmg / win 在线安装器):
1. 请求各渠道官方**稳定 api 端点**(每次重新签发下载直链),跟随 `302` 从官方文件名解析版本。
2. 该版本 Release **已存在则跳过**;否则在 runner 上下载并发布新 Release。
3. macOS 附带尝试同版本的增量 `tar.gz`(未发布则自动跳过)。
4. 逐文件 `SHA256`,连同安装包一并上传。

**`offline-win` 任务**(Windows 完整离线安装包 ~830 MB):
- 官方下载按钮只给在线安装器,离线完整包**无干净官方端点**;唯一跟踪其确切 CDN 直链的是社区整理索引。
- 从该索引取**最新离线包直链 + 产品版本 `V6.x`**,走网易裸 CDN 直链下载,发布为 `win-cn-offline-V6.x`。
- 索引拉取/解析失败则**跳过**,不影响其它任务。此为唯一的第三方依赖,页面改版时需同步维护。

**`backfill-mac` 任务**(macOS 历史版本补全 · 每周日 / 手动 `backfill=yes`):
- 遍历候选版本号,逐个 `HEAD` 探测 4 类直链(dmg / tar.gz × CN / Global),把网易 CDN 上**还活着的历史包**补成 `mac-<渠道>-<版本>`(标 pre-release)。
- 网易对老版本保留**不规律**(有的只留 dmg、有的只留 tar.gz、有的全删),能补到哪算哪。已存在的 release 跳过。

也可在 **Actions → Sync MuMu → Run workflow** 手动触发(可选只同步某一渠道)。

---

## ⚖️ 声明

本仓库仅镜像网易 MuMu **官方公开分发**的安装包,不含任何破解 / 授权绕过 / 二进制修改。
版权归网易(NetEase)所有,请遵守 MuMu 官方用户协议。官方站点:
[mumu.163.com](https://mumu.163.com)(中国版)· [mumuplayer.com](https://www.mumuplayer.com)(国际版)。
