# mumu-release

MuMu 模拟器 / MuMuPlayer Pro 官方安装包自动镜像 · Automated mirror of official MuMu installers (macOS / Windows · 中国版 + 国际版).

自动从**网易官方源**拉取**未经修改的官方原版**安装包,按版本归档到 GitHub Releases,每天检查一次,有新版自动发布。**同一版本的中国版 + 国际版合并在同一个 Release**(文件名自带 `default` / `global` 区分)。按 tag 前缀分三类:

| tag 前缀 | 内容 | 平台 |
|---|---|---|
| `mac-<版本>` | MuMuPlayer Pro 完整 `dmg` + 完整 `tar.gz`(均 Apple Silicon,两种都能装) | macOS |
| `win-<产品版本>` | 中国版完整离线安装包 `exe`(合体版 ~830 MB,免联网双击直装) | Windows |
| `win-cn-offline-<版本>` | 中国版完整离线安装包 `exe`(三引擎:mumu15 安卓15 / nemux 安卓12 / nxmain) | Windows |
| `win-global-offline-<版本>` | 国际版完整离线安装包 `exe`(三引擎:mumu15 安卓15 / nemux 安卓12 / nxmain) | Windows |
| `win-installer-<版本>` | 官方在线安装器 `exe`(小巧下载器,运行后再联网拉完整包) | Windows |

## 下载

到 **[Releases](../../releases)** 按前缀找对应平台,或看 **[Latest](../../releases/latest)**(指向最新 macOS 版)。每个 Release 附 `checksums.sha256` 校验和。

- **macOS**:`MuMuPlayer_<ver>_default.dmg`(中国版)/ `_global.dmg`(国际版)· `MuMuUpdater_<ver>_default.tar.gz`(中国版完整包)/ `MuMuMacUpdater_<ver>-global.tar.gz`(国际版完整包)
- **Windows 完整包(中国版·合体版)**:`MuMu-setup-V<ver>-<build>.exe`(免联网直装)
- **Windows 完整包(中国版·分引擎)**:`MuMu-setup-{mumu15,nemux,nxmain}-V<ver>-*.exe`(按引擎分:安卓15 / 安卓12 / NX 主)
- **Windows 完整包(国际版)**:`MuMu-setup-{mumu15,nemux,nxmain}-V<ver>-overseas-*.exe`(按引擎分:安卓15 / 安卓12 / NX 主)
- **Windows 在线安装器**:`MuMu_<ver>_gw-win_*.exe`(中国版)/ `MuMu_<ver>_gw-overseas12_*.exe`(国际版)

## 说明

全部文件**未经任何修改**,逐字节镜像自网易官方 CDN,仅作下载加速 / 归档留存。版权归网易(NetEase)所有,请遵守 MuMu 官方用户协议。官方站点:[mumu.163.com](https://mumu.163.com)(中国版)· [mumuplayer.com](https://www.mumuplayer.com)(国际版)。
