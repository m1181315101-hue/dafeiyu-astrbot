"""相册：照片文件夹里的对照表 photos.json 和挑图规则。不依赖 AstrBot，测试可以直接加载。

photos.json 按文件名记每张照片（字段都可以不写，没写进表的照片当普通自拍）：
    kind      自拍 / 生活照 / 合照
    with      合照里的同事，比如 ["Claude"]；全员合照把七位都写上
    scene     一句话说照片里是什么，发出去后告诉她，她顺着这句配话
    keywords  聊到这些词时优先挑这张
    times     只在这些时段随手发：早上 中午 下午 晚上 深夜
    seasons   只在这些季节随手发：春 夏 秋 冬
    festival  节日照，只在节日前后几天随手发：春节 中秋 万圣节 圣诞 元旦 情人节
    ask_only  true 表示不随手发，聊到 keywords 才发（下雨、委屈这类）
带 times / seasons / festival / ask_only 的照片，条件不对时只有聊到它的关键词、或者点名要看照片里的同事才会挑到。
"""
import datetime
import json
import os
import random

INDEX = "photos.json"
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
KINDS = ("自拍", "生活照", "合照")
MATES = ("Claude", "GPT", "Gemini", "Grok", "GLM", "Kimi", "千问")
ALIASES = {"gork": "Grok", "qwen": "千问", "通义": "千问", "通义千问": "千问", "chatgpt": "GPT",
           "智谱": "GLM", "智谱清言": "GLM", "克劳德": "Claude"}
EVERYONE = ("大家", "全员", "所有人", "大合照", "全家福", "同事们")
TZ = datetime.timezone(datetime.timedelta(hours=8))  # 按北京时间算时段和节日
TIMES = {"早上": range(5, 10), "中午": range(10, 14), "下午": range(14, 18), "晚上": range(18, 23),
         "深夜": (23, 0, 1, 2, 3, 4)}
SEASONS = {"春": (3, 4, 5), "夏": (6, 7, 8), "秋": (9, 10, 11), "冬": (12, 1, 2)}
# 春节、中秋按农历，每年日期不一样，先写到 2031 年；过了这几年要往后补
LUNAR = {
    "春节": ("2026-02-17", "2027-02-06", "2028-01-26", "2029-02-13", "2030-02-03", "2031-01-23"),
    "中秋": ("2026-09-25", "2027-09-15", "2028-10-03", "2029-09-22", "2030-09-12", "2031-10-01"),
}
FIXED = {"万圣节": "10-31", "圣诞": "12-25", "元旦": "01-01", "情人节": "02-14"}
WINDOW = {"春节": (-7, 8)}  # 除夕前一周到元宵；其余节日前后 3 天


def festival_on(name: str, today: datetime.date) -> bool:
    before, after = WINDOW.get(name, (-3, 3))
    if name in LUNAR:
        days = [datetime.date.fromisoformat(d) for d in LUNAR[name]]
    elif name in FIXED:
        days = [datetime.date.fromisoformat(f"{y}-{FIXED[name]}") for y in (today.year - 1, today.year, today.year + 1)]
    else:
        return False
    return any(before <= (today - d).days <= after for d in days)


def time_of_day(hour: int) -> str:
    return next(name for name, hours in TIMES.items() if hour in hours)


def mate_name(text: str) -> str:
    """「gork」「通义千问」「大家」→ 相册里写的名字；认不出就原样返回"""
    t = (text or "").strip()
    if not t:
        return ""
    if t in EVERYONE:
        return "全员"
    for m in MATES:
        if t.lower() == m.lower():
            return m
    return ALIASES.get(t.lower(), t)


def load(photo_dir: str) -> tuple[list[dict], str]:
    """文件夹里的照片 + 对照表。返回 (照片列表, 对照表出错时的说明)"""
    try:
        names = sorted(n for n in os.listdir(photo_dir) if n.lower().endswith(PHOTO_EXTS) and not n.startswith("."))
    except OSError:
        return [], ""
    index, problem = {}, ""
    try:
        with open(os.path.join(photo_dir, INDEX), encoding="utf-8") as f:
            index = json.load(f)
        if not isinstance(index, dict):
            index, problem = {}, f"{INDEX} 不是按文件名记的对象"
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        problem = f"{INDEX} 读不了：{e}"
    photos = []
    for n in names:
        meta = index.get(n) if isinstance(index.get(n), dict) else {}
        kind = meta.get("kind") if meta.get("kind") in KINDS else "自拍"
        photos.append({
            "file": n, "path": os.path.join(photo_dir, n), "kind": kind,
            "with": [mate_name(x) for x in meta.get("with") or []],
            "scene": str(meta.get("scene") or ""),
            "keywords": [str(k) for k in meta.get("keywords") or [] if str(k).strip()],
            "times": list(meta.get("times") or []), "seasons": list(meta.get("seasons") or []),
            "festival": str(meta.get("festival") or ""), "ask_only": bool(meta.get("ask_only")),
        })
    return photos, problem


def fits_now(p: dict, now: datetime.datetime) -> bool:
    """不点名、不聊到时，这张照片现在能不能随手发"""
    if p["ask_only"]:
        return False
    if p["times"] and time_of_day(now.hour) not in p["times"]:
        return False
    if p["seasons"] and not any(now.month in SEASONS.get(s, ()) for s in p["seasons"]):
        return False
    if p["festival"] and not festival_on(p["festival"], now.date()):
        return False
    return True


def pick(photos: list[dict], kind: str = "", with_whom: str = "", scene: str = "",
         recent: list[str] = (), now: datetime.datetime | None = None,
         rng: random.Random | None = None) -> tuple[dict | None, str]:
    """挑一张。返回 (照片, 挑不出时给她的说明)"""
    rng = rng or random
    now = now or datetime.datetime.now(TZ)
    who = mate_name(with_whom)
    kind = (kind or "").strip()
    if not who and kind in ("", "合照"):  # 同事名写进了 scene 里也认；明说要自拍、生活照时不算
        low = (scene or "").lower()
        who = next((m for m in MATES if m.lower() in low), "") or \
            next((v for k, v in ALIASES.items() if k in low), "")
    if who:
        kind = "合照"
    pool = photos
    if kind in KINDS:
        pool = [p for p in pool if p["kind"] == kind]
        if not pool:
            return None, f"你相册里没有{kind}。"
    if who == "全员":
        pool = [p for p in pool if len(p["with"]) >= 3]
    elif who:
        pool = [p for p in pool if who in p["with"]]
    if who and not pool:
        return None, f"你相册里没有和{who}的合照。" if who != "全员" else "你相册里没有大家一起的合照。"

    query = " ".join([scene or "", kind])

    def score(p):
        s = sum(2 for k in p["keywords"] if k in query)
        if p["festival"] and p["festival"] in query:
            s += 2
        if who and who != "全员" and len(p["with"]) == 1:
            s += 1  # 点名看谁，优先单独和她的那张
        return s

    scored = [(score(p), p) for p in pool]
    hits = [(s, p) for s, p in scored if s > 0]
    if hits:
        top = max(s for s, _ in hits)
        cands = [p for s, p in hits if s == top]
    elif who:
        cands = pool  # 点名看同事：不管节日季节，有就发
    else:
        cands = [p for p in pool if fits_now(p, now)] or [p for p in pool if not p["ask_only"]] or pool
    fresh = [p for p in cands if p["file"] not in recent]
    return rng.choice(fresh or cands), ""
