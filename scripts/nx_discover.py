#!/usr/bin/env python3
# 自动发现 MuMu 完整离线安装包直链 —— 复刻官方在线安装器 nemu-downloader 的
# .../api/v2/download/nx 请求(逆向自 6.0.x 安装器)。用法: nx_discover.py [global|cn]
#
# 关键点(全部逆向实证):
#   · 请求体 = application/x-www-form-urlencoded(不是 JSON!),字段按名排序。
#   · 签名 X-Param-SIGN = HMAC-SHA256(PROD密钥, "POST"+path+排序小写X-Param头(含空值,k=v用&连)+body),小写 hex。
#   · machine = 一段普通 JSON 字符串(键排序、": "/", " 分隔),服务器**不校验真实硬件**,合成假指纹即可过。
#   · detectinfo 留空;product 字段留空;has_installed="0"。
#   · ★usage 是配置区分键:国际版=1、国内版=0;发错会 errcode 101「配置不存在」。
#   · 返回 data.components[].link 即每引擎完整离线 setup exe 直链(mumu15=安卓15/nemux=安卓12/nxmain=NX主)。
# 输出到 stdout:第一行 VERSION=<data.version>,后续每行一条 https 直链(已归一到 netease CDN)。
# 失败(密钥缺失/网络/风控/地理围栏)→ 退出码 1,无输出;上层 sync.sh 据此回退内置直链或社区索引。
#
# 地理:国际版 api.mumuglobal.com 从任意 IP(含 GitHub Azure US)可达;
#       国内版 api.mumu.nie.netease.com 需**中国大陆出口 IP**(US runner 会 errcode 101)。
import os, sys, json, uuid, time, hmac, hashlib, ssl, urllib.request, urllib.error, urllib.parse

# 请求签名密钥从环境变量注入(仓库 Secret: MUMU_NX_SECRET),不硬编码进公开仓库。
SECRET = os.environ.get("MUMU_NX_SECRET", "").encode()
PATH   = "/api/v2/download/nx"
CTX    = ssl.create_default_context()

REGIONS = {
    "global": dict(host="api.mumuglobal.com",       chn="gw-overseas12", vn="6.0.2",
                   usage="1", lang="en",      cnt="US", pkgn="com.netease.mumu.nx"),
    "cn":     dict(host="api.mumu.nie.netease.com",  chn="gw-win",        vn="6.0.3",
                   usage="0", lang="zh-Hans", cnt="CN", pkgn="com.netease.mumu"),
}

# 合成的通用 Windows 硬件指纹(纯占位,服务器不校验真伪)
MACHINE = {
    "base_board": "Manufacturer:ASUSTeK COMPUTER INC.Product:PRIME B550M-A",
    "cpu": "AMD Ryzen 5 5600G with Radeon Graphics",
    "hard_disk": ["DRIVE_FIXED(C:\\):Total disk space:476.9GBFree disk space:210.3GB"],
    "hyperv_opened": 0, "ip": "1.2.3.4", "mac": "AA:BB:CC:DD:EE:FF", "memory": 16000,
    "os": "Windows 11 64-bit Kernel 10.0.22631",
    "screen": {"height": 1080, "width": 1920},
    "screen_list": [{"dpr": 1, "height": 1080, "is_primary": 1, "width": 1920}],
    "supported_install_arc": "x86_64", "video": ["NVIDIA GeForce RTX 3060"],
    "vt": "Intel/AMD virtualization technology detected.", "vt_enabled": 1, "vt_supported": 1,
}
MACHINE_STR = json.dumps(MACHINE, sort_keys=True, separators=(", ", ": "), ensure_ascii=False)


def headers(u, r):
    vn = r["vn"]
    return {
        "X-Param-PLAT": "1", "X-Param-NG": "NXMAIN", "X-Param-client-id": u, "X-Param-UUID": u,
        "X-Param-VN": vn, "X-Param-VC": vn.replace(".", ""), "X-Param-PKGN": r["pkgn"],
        "X-Param-CHN": r["chn"], "X-Param-FCHN": r["chn"], "X-Param-LANG": r["lang"], "X-Param-CNT": r["cnt"],
        "X-Param-TS": str(int(time.time() * 1000)), "X-Param-System-ID": u,
        "X-Param-NONCE": uuid.uuid4().hex[:16], "X-Param-ENT": "", "X-Param-user-id": "",
        "X-Param-device-id": "", "X-Param-TDID": "", "X-Param-OAID": "", "X-Param-PRODUCT": "NX",
        "X-Param-PRODUCT-VN": vn, "X-Param-CAMPAIGN": "", "X-Param-ARCH": "x86_64",
        "X-Param-TZ-OFFSET": "-480",
    }


def sign(h, body):
    items = sorted(((k, v) for k, v in h.items() if k.lower().startswith("x-param-")),
                   key=lambda kv: kv[0].lower())
    msg = "POST" + PATH + "&".join(f"{k.lower()}={v}" for k, v in items) + body
    return hmac.new(SECRET, msg.encode(), hashlib.sha256).hexdigest()


def call_nx(r):
    u = str(uuid.uuid4())
    fields = {
        "architecture": "x86_64", "channel": r["chn"], "detectinfo": "", "downloader_version": r["vn"],
        "has_installed": "0", "language": r["lang"], "machine": MACHINE_STR, "n": "MuMu_setup",
        "package": "", "product": "", "usage": r["usage"], "uuid": u,
    }
    body = urllib.parse.urlencode(fields)
    h = headers(u, r)
    h["X-Param-SIGN"] = sign(h, body)
    h["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request("https://" + r["host"] + PATH, data=body.encode(), method="POST")
    for k, v in h.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def main():
    region = sys.argv[1] if len(sys.argv) > 1 else "global"
    if region not in REGIONS:
        print(f"unknown region: {region} (use global|cn)", file=sys.stderr)
        return 2
    if not SECRET:
        print("MUMU_NX_SECRET 未设置,跳过 nx 自动发现(上层将回退)", file=sys.stderr)
        return 1
    try:
        j = call_nx(REGIONS[region])
    except Exception as e:  # 网络 / TLS / 解析
        print(f"nx request failed ({region}): {e}", file=sys.stderr)
        return 1
    if j.get("errcode") != 100:
        # errcode 101「配置不存在」多半是地理围栏(CN 需中国 IP)或参数不符
        print(f"nx business error ({region}): {j.get('errcode')} {j.get('errmsg')}", file=sys.stderr)
        return 1
    data = j.get("data") or {}
    comps = data.get("components") or []
    if not comps:
        print(f"nx returned no components ({region})", file=sys.stderr)
        return 1
    print("VERSION=" + str(data.get("version", "")))
    for c in comps:
        link = c.get("link") or ""
        if not link:
            continue
        # easebar/http → netease/https(同名镜像,ensure_release 用 https HEAD 校验)
        link = link.replace("http://a11.gdl.easebar.com/", "https://a11.gdl.netease.com/")
        link = link.replace("http://", "https://")
        print(link)
    return 0


if __name__ == "__main__":
    sys.exit(main())
