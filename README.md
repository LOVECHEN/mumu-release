# MuMuPlayer / MuMu 模拟器官方下载与历史版本

[中文](#中文) | [English](#english)

## 中文

网易 **MuMuPlayer（MuMu 模拟器 / MuMu Player / MuMu Emulator）** 官方下载镜像与历史版本归档。提供 MuMuPlayer Pro for Mac / macOS Apple Silicon 原版 `dmg`，以及 Windows x86-64、Windows ARM 官方安装器和离线安装资源。中国版与国际版按版本合并归档。

发现新版本或现有 Release 缺少官方文件时，任务会自动补充并发布。相同版本的中国版与国际版文件合并到同一个 Release：

| Tag 前缀 | 内容 | 平台 |
|---|---|---|
| `mac-<版本>` | MuMuPlayer Pro 完整包 `dmg` / `tar.gz` | macOS · Apple Silicon |
| `win-<版本>` | 在线安装器 / 合体版 / 三引擎完整包 `exe` | Windows · x86-64 |
| `win-arm-<版本>` | MuMuPlayer ARM 安装包 `exe` | Windows · ARM64 |

### 下载

到 **[GitHub Releases](https://github.com/LOVECHEN/mumu-release/releases)** 按 Tag 前缀选择平台，或打开 **[Latest Release](https://github.com/LOVECHEN/mumu-release/releases/latest)**。每个 Release 都附带 `checksums.sha256` 校验文件。

- **macOS**：`MuMuPlayer_<ver>_default.dmg`（中国版）、`MuMuPlayer_<ver>_global.dmg`（国际版）、`MuMuPlayer_<ver>_{default,global}.tar.gz`（新版完整包）、`MuMuUpdater_<ver>_default.tar.gz` / `MuMuMacUpdater_<ver>-global.tar.gz`（旧版完整包）。
- **Windows**：`MuMu_<ver>_gw-win_*.exe` / `MuMu_<ver>_gw-overseas12_*.exe`（在线安装器）、`MuMu-setup-V<ver>-<build>.exe`（中国合体版）、`MuMu-setup-{mumu15,nemux,nxmain}-V<ver>-*.exe` / `MuMu-setup-{mumu15,nemux,nxmain}-V<ver>-overseas-*.exe`（国内 / 国际分引擎完整包）。
- **Windows ARM**：`MuMuARM_<ver>_gw-arm-beta.exe`（中国版新版）、`MuMuARM_<ver>-global_gw-arm-download.exe`（国际版）或 `MuMuPlayerARM_<ver>_gw-update-armbeta.exe`（旧版）。

### Windows 安装

- 中国合体版 `MuMu-setup-V<ver>-<build>.exe` 可直接运行安装。
- 在线安装器体积较小，会按所选版本和引擎下载完整资源。`mumu15`、`nemux`、`nxmain` 分别是安卓 15、安卓 12、NX 主引擎资源；全新安装通常由在线安装器自动选择和组合，不需要逐个手动运行。

如果在线安装器从官方 CDN 下载较慢，可以先从本仓库下载它需要的完整资源，让安装器直接复用本地文件：

1. 下载对应渠道的在线安装器和完整资源。国际版文件名包含 `gw-overseas12` / `overseas`，中国版不含 `overseas`，两种渠道不要混用。
2. 保持完整资源的原始文件名不变。按 `Win + R`，输入 `%TEMP%` 并回车，将资源复制到打开的目录。
3. 运行在线安装器。文件名、版本和校验值完全匹配时，安装器会跳过对应资源的重复下载；不匹配时会重新下载。

国际版全新安装默认使用 `mumu15` + `nxmain`；选择安卓 12 等其他方案时还可能需要 `nemux` 或其他资源。这个方法用于解决官方 CDN 下载慢的问题，安装器仍需联网获取版本信息，不等同于完全离线安装。

### 说明

全部文件未经修改，逐字节镜像自网易官方 CDN，仅作下载加速和历史归档。版权归网易（NetEase）所有。官方站点：[mumu.163.com](https://mumu.163.com)（中国版）和 [mumuplayer.com](https://www.mumuplayer.com)（国际版）。

## English

Official NetEase **MuMuPlayer (MuMu Emulator / MuMu Player)** downloads and historical version archive. It provides original MuMuPlayer Pro for Mac / macOS Apple Silicon `dmg` files, plus official Windows x86-64 and Windows ARM installers and offline resources. Chinese and global files with the same version are grouped into one Release.

When a new version appears, or an existing Release is missing an official file, the automation adds and publishes it. Chinese and global files with the same version are merged into the same Release:

| Tag prefix | Contents | Platform |
|---|---|---|
| `mac-<version>` | Complete MuMuPlayer Pro `dmg` / `tar.gz` packages | macOS · Apple Silicon |
| `win-<version>` | Online installer / all-in-one / three-engine complete `exe` packages | Windows · x86-64 |
| `win-arm-<version>` | MuMuPlayer ARM installer `exe` | Windows · ARM64 |

### Downloads

Open **[GitHub Releases](https://github.com/LOVECHEN/mumu-release/releases)** and select a platform by Tag prefix, or open the **[Latest Release](https://github.com/LOVECHEN/mumu-release/releases/latest)**. Every Release includes a `checksums.sha256` file.

- **macOS**: `MuMuPlayer_<ver>_default.dmg` (Chinese), `MuMuPlayer_<ver>_global.dmg` (global), `MuMuPlayer_<ver>_{default,global}.tar.gz` (current complete packages), and `MuMuUpdater_<ver>_default.tar.gz` / `MuMuMacUpdater_<ver>-global.tar.gz` (legacy complete package names).
- **Windows**: `MuMu_<ver>_gw-win_*.exe` / `MuMu_<ver>_gw-overseas12_*.exe` (online installers), `MuMu-setup-V<ver>-<build>.exe` (Chinese all-in-one package), and `MuMu-setup-{mumu15,nemux,nxmain}-V<ver>-*.exe` / `MuMu-setup-{mumu15,nemux,nxmain}-V<ver>-overseas-*.exe` (Chinese/global engine packages).
- **Windows ARM**: `MuMuARM_<ver>_gw-arm-beta.exe` (current Chinese build), `MuMuARM_<ver>-global_gw-arm-download.exe` (global build), or `MuMuPlayerARM_<ver>_gw-update-armbeta.exe` (legacy naming).

### Windows installation

- Run the Chinese all-in-one `MuMu-setup-V<ver>-<build>.exe` package directly.
- The smaller online installer downloads the complete resources for the selected version and engine. `mumu15`, `nemux`, and `nxmain` are the Android 15, Android 12, and NX main-engine resources. For a fresh installation, the online installer normally selects and combines the required resources automatically.

If downloads from the official CDN are slow, download the required complete resources from this repository first and let the online installer reuse them locally:

1. Download the online installer and complete resources for the same channel. Global filenames contain `gw-overseas12` / `overseas`; Chinese filenames do not. Do not mix the two channels.
2. Keep the original resource filenames unchanged. Press `Win + R`, enter `%TEMP%`, and copy the resources into the opened directory.
3. Run the online installer. It skips a resource download when the filename, version, and checksum match; otherwise, it downloads the resource again.

A new global installation normally uses `mumu15` + `nxmain`. Android 12 or another configuration may also require `nemux` or additional resources. This method helps with slow official CDN downloads, but the installer still needs an internet connection to retrieve version metadata and is not a fully offline installation.

### Notes

All files are mirrored byte-for-byte from NetEase's official CDN without modification, for download acceleration and historical archiving. Copyright belongs to NetEase. Official sites: [mumu.163.com](https://mumu.163.com) (Chinese) and [mumuplayer.com](https://www.mumuplayer.com) (global).
