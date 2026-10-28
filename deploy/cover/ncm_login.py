"""网易云扫码登录：生成二维码图片，用网易云 App 扫码确认后，把登录 cookie 存到 ncm_cookie.txt（只有你能读）。

用法（先确保 ncm-api 容器在跑）：.venv/bin/python ncm_login.py [二维码图片保存路径]
不打印 cookie 本身；之后翻唱服务每次找歌时从 ncm_cookie.txt 读出来带上。
"""

import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
API = CFG.get("ncm_api", "http://127.0.0.1:3000")
COOKIE_FILE = os.path.join(ROOT, "ncm_cookie.txt")


def call(path: str, **params) -> dict:
    # 接口按 URL 缓存 2 分钟，时间戳要放在 URL 上，不然一直拿到旧状态
    url = f"{API}{path}?timestamp={int(time.time() * 1000)}"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST")
    return json.load(urllib.request.urlopen(req, timeout=20))


def main() -> None:
    qr_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ncm-login-qr.png")
    key = call("/login/qr/key")["data"]["unikey"]
    img = call("/login/qr/create", key=key, qrimg="true")["data"]["qrimg"]
    with open(qr_path, "wb") as f:
        f.write(base64.b64decode(img.split(",", 1)[1]))
    print(f"二维码已生成：{qr_path}（大约 2 分钟内有效）", flush=True)
    last = None
    for _ in range(90):
        time.sleep(2)
        r = call("/login/qr/check", key=key)
        code = r.get("code")
        if code != last:
            print({800: "二维码过期了，重新运行", 801: "等待扫码", 802: "已扫码，请在手机上确认",
                   803: "登录成功"}.get(code, f"状态 {code}"), flush=True)
            last = code
        if code == 800:
            sys.exit(1)
        if code == 803:
            fd = os.open(COOKIE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(r["cookie"])
            status = call("/login/status", cookie=r["cookie"]).get("data") or {}
            profile = status.get("profile") or {}
            print(f"cookie 已保存到 {COOKIE_FILE}；vipType={profile.get('vipType')}", flush=True)
            return
    print("等太久了，重新运行", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
