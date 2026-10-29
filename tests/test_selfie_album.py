# -*- coding: utf-8 -*-
"""自拍插件的相册挑图测试：对照表读取、按类型/同事/场景挑、节日和时段、不重复。

跑法（纯标准库，不需要 AstrBot 环境）：
    python tests/test_selfie_album.py
"""
import datetime
import importlib.util
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("album", os.path.join(ROOT, "plugin", "astrbot_plugin_selfie", "album.py"))
album = importlib.util.module_from_spec(spec)
spec.loader.exec_module(album)

TZ = album.TZ
NOON_OCT = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=TZ)
MATES = ["Claude", "GPT", "Gemini", "Grok", "GLM", "Kimi", "千问"]
INDEX = {
    "a_原自拍.jpg": {},
    "b_白饭.jpg": {"kind": "自拍", "scene": "捧着一大碗白饭", "keywords": ["吃饭", "白饭"]},
    "c_晚安.jpg": {"kind": "自拍", "scene": "裹着被子说晚安", "keywords": ["晚安", "睡觉"], "times": ["晚上", "深夜"]},
    "d_委屈.jpg": {"kind": "自拍", "scene": "眼睛水汪汪", "keywords": ["委屈"], "ask_only": True},
    "e_下雨.jpg": {"kind": "生活照", "scene": "撑着透明雨伞", "keywords": ["下雨", "雨"], "ask_only": True},
    "f_樱花.jpg": {"kind": "生活照", "scene": "樱花树下", "keywords": ["春天", "樱花"], "seasons": ["春"]},
    "g_银杏.jpg": {"kind": "生活照", "scene": "银杏路上捧烤红薯", "keywords": ["秋天"], "seasons": ["秋"]},
    "h_和Claude.jpg": {"kind": "合照", "with": ["Claude"], "scene": "咖啡馆吃蛋糕", "keywords": ["蛋糕"]},
    "i_和Grok.jpg": {"kind": "合照", "with": ["Grok"], "scene": "万圣节做鬼脸", "keywords": ["万圣节"], "festival": "万圣节"},
    "j_和千问.jpg": {"kind": "合照", "with": ["千问"], "scene": "春节包饺子", "keywords": ["过年", "饺子"], "festival": "春节"},
    "k_全员.jpg": {"kind": "合照", "with": MATES, "scene": "圣诞大合照", "keywords": ["圣诞"], "festival": "圣诞"},
    "l_海边全员.jpg": {"kind": "合照", "with": MATES, "scene": "海边大合照", "keywords": ["海边", "游泳"], "ask_only": True},
}

failed = 0


def check(name, cond):
    global failed
    print(("  ok  " if cond else "  FAIL ") + name)
    if not cond:
        failed += 1


def make_dir(index, extra=()):
    d = tempfile.mkdtemp()
    for n in list(index) + list(extra):
        open(os.path.join(d, n), "wb").close()
    if index is not None:
        with open(os.path.join(d, album.INDEX), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    return d


def pick(photos, **kw):
    kw.setdefault("now", NOON_OCT)
    kw.setdefault("rng", random.Random(1))
    return album.pick(photos, **kw)


print("1. 读相册")
d = make_dir(INDEX, extra=["z_没写进表.png", "notes.txt"])
photos, problem = album.load(d)
by = {p["file"]: p for p in photos}
check("txt 不算照片，没写进表的照片也在", len(photos) == len(INDEX) + 1 and "notes.txt" not in by)
check("没写进表的当普通自拍", by["z_没写进表.png"]["kind"] == "自拍" and not by["z_没写进表.png"]["scene"])
check("对照表正常时没有报错", problem == "")
bad = tempfile.mkdtemp()
open(os.path.join(bad, "x.jpg"), "wb").close()
open(os.path.join(bad, album.INDEX), "w").write("{坏掉的")
p2, problem2 = album.load(bad)
check("对照表坏了照样能发，全当自拍，并说明原因", len(p2) == 1 and p2[0]["kind"] == "自拍" and album.INDEX in problem2)

print("2. 点名看同事")
p, why = pick(photos, with_whom="Grok")
check("看 Grok：不在万圣节也发和 Grok 的合照", p and p["file"] == "i_和Grok.jpg")
p, _ = pick(photos, with_whom="gork")
check("写成 gork 也认得", p and p["file"] == "i_和Grok.jpg")
p, _ = pick(photos, with_whom="通义千问")
check("通义千问 → 千问", p and p["file"] == "j_和千问.jpg")
p, _ = pick(photos, with_whom="Claude")
check("看 Claude：单独合照优先于全员合照", p and p["file"] == "h_和Claude.jpg")
p, _ = pick(photos, with_whom="GLM")
check("看 GLM：没有单独合照就发全员那张", p and p["file"] == "k_全员.jpg")
seen = {pick(photos, with_whom="大家", rng=random.Random(i))[0]["file"] for i in range(100)}
check("看大家：发全员合照，不挑只在聊到时才发的海边那张", seen == {"k_全员.jpg"})
p, _ = pick(photos, with_whom="大家", scene="去海边吧")
check("看大家又聊到海边：发海边那张", p and p["file"] == "l_海边全员.jpg")
p, _ = pick(photos, scene="想看你和kimi")
check("同事名写在场景里也认（Kimi 没单独合照就发全员）", p and p["file"] == "k_全员.jpg")
p, _ = pick(photos, kind="自拍", scene="GPT 说你委屈巴巴的")
check("明说要自拍时，场景里的同事名不把它变成合照", p and p["file"] == "d_委屈.jpg")
p, why = pick(photos, with_whom="豆包")
check("没有的同事：不发，说没有", p is None and "豆包" in why)

print("3. 按类型和场景")
p, _ = pick(photos, scene="下雨了")
check("聊到下雨：发撑伞那张（平时不随手发）", p and p["file"] == "e_下雨.jpg")
p, _ = pick(photos, kind="自拍", scene="晚安啦")
check("中午说晚安也发晚安那张（点到了关键词）", p and p["file"] == "c_晚安.jpg")
p, _ = pick(photos, scene="过年好")
check("聊到过年：发包饺子那张", p and p["file"] == "j_和千问.jpg")
p, why = pick([x for x in photos if x["kind"] != "生活照"], kind="生活照")
check("没有这一类：不发，说没有", p is None and "生活照" in why)
seen = {pick(photos, kind="自拍", rng=random.Random(i))[0]["file"] for i in range(200)}
check("要自拍只发自拍", seen <= {"a_原自拍.jpg", "b_白饭.jpg", "z_没写进表.png"})

print("4. 随手发：看时段、季节、节日")
seen = {pick(photos, rng=random.Random(i))[0]["file"] for i in range(400)}
check("十月中午：不发晚安、委屈、下雨、樱花，不发春节、圣诞、万圣节照", not seen & {
    "c_晚安.jpg", "d_委屈.jpg", "e_下雨.jpg", "f_樱花.jpg", "i_和Grok.jpg", "j_和千问.jpg", "k_全员.jpg"})
check("十月中午：秋天的银杏能发", "g_银杏.jpg" in seen)
night = datetime.datetime(2026, 10, 20, 23, 30, tzinfo=TZ)
seen = {pick(photos, now=night, rng=random.Random(i))[0]["file"] for i in range(400)}
check("深夜能随手发晚安那张", "c_晚安.jpg" in seen)
halloween = datetime.datetime(2026, 10, 30, 15, 0, tzinfo=TZ)
seen = {pick(photos, now=halloween, rng=random.Random(i))[0]["file"] for i in range(400)}
check("万圣节前一天能随手发和 Grok 的万圣节合照", "i_和Grok.jpg" in seen)
check("春节：除夕前五天算，节后两周不算",
      album.festival_on("春节", datetime.date(2027, 2, 1)) and not album.festival_on("春节", datetime.date(2027, 2, 20)))
check("圣诞：跨年前后按日期算", album.festival_on("圣诞", datetime.date(2026, 12, 27))
      and not album.festival_on("圣诞", datetime.date(2026, 12, 10)))
check("元旦：12 月 30 日算（用到上一年/下一年的日期）", album.festival_on("元旦", datetime.date(2026, 12, 30)))

print("5. 不重复")
p, _ = pick(photos, kind="自拍", recent=["a_原自拍.jpg", "z_没写进表.png"])
check("最近发过的先跳过", p and p["file"] == "b_白饭.jpg")
p, _ = pick(photos, with_whom="Grok", recent=["i_和Grok.jpg"])
check("只有一张时照样发", p and p["file"] == "i_和Grok.jpg")

print("失败 %d 项" % failed if failed else "全部通过")
sys.exit(1 if failed else 0)
