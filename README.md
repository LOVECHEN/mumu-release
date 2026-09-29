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
| 🪟 **Windows** | 中国版 | 全量 `exe`(64-bit) | [![win-cn](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-cn-*&label=版本&color=4c8bf5)](https://github.com/LOVECHEN/mumu-release/releases?q=win-cn) |
| 🪟 **Windows** | 国际版 | 全量 `exe`(64-bit) | [![win-global](https://img.shields.io/github/v/release/LOVECHEN/mumu-release?filter=win-global-*&label=版本&color=6f42c1)](https://github.com/LOVECHEN/mumu-release/releases?q=win-global) |

> - **macOS = MuMuPlayer Pro**(版本号 `1.9.x`,Apple Silicon 原生 dmg;中国版另附增量热更 `tar.gz`)。
> - **Windows = MuMu 模拟器 12**(版本号 `6.0.x`,64-bit exe)。macOS 与 Windows 是两条独立产品线,版本号互不相干。
> - 资产**保留官方原名**,例:mac `MuMuPlayer_1.9.6_default.dmg`、win `MuMu_6.0.3_gw-win_zh-Hans_*.exe`。
> - 每个版本一个独立 Release,历史累积**永不删除**。仓库 **Latest** = macOS 中国版最新。

---

## 🔄 工作原理

[`.github/workflows/sync.yml`](.github/workflows/sync.yml) 每天 **06:00 UTC(北京 14:00)** 运行:

1. 请求各渠道官方**稳定 api 端点**(每次重新签发下载直链)。
2. 跟随 `302` 重定向,从官方文件名解析最新版本号。
3. 该版本对应 Release **已存在则跳过**;否则在 runner 上下载安装包并发布新 Release。
4. macOS 附带尝试同版本的增量 `tar.gz`(未发布则自动跳过,如国际版 1.9.x)。
5. 逐文件计算 `SHA256`,连同安装包一并上传。

也可在 **Actions → Sync MuMu → Run workflow** 手动触发(可选只同步某一渠道)。

---

## ⚖️ 声明

本仓库仅镜像网易 MuMu **官方公开分发**的安装包,不含任何破解 / 授权绕过 / 二进制修改。
版权归网易(NetEase)所有,请遵守 MuMu 官方用户协议。官方站点:
[mumu.163.com](https://mumu.163.com)(中国版)· [mumuplayer.com](https://www.mumuplayer.com)(国际版)。
