# -*- coding: utf-8 -*-
"""表情转换（大肥鱼工具箱 face 模块，原 face_convert）回归测试：嘴硬橡皮擦不误删 + file:// 路径解析 + 身份标记认人。

跑法（纯标准库，不需要 AstrBot 环境）：
    python tests/test_face_rules.py
原理：用空壳模块把 astrbot 依赖桩掉，直接加载插件源码，测纯逻辑。
"""
import importlib.util
import logging
import os
import re
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "plugin", "astrbot_plugin_dafeiyu", "modules", "face.py")


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Star:
    def __init__(self, *a, **k):
        pass


def _register(*a, **k):
    def deco(cls):
        return cls

    return deco


class _Filter:  # filter.xxx(...) 全都变成空装饰器
    EventMessageType = types.SimpleNamespace(ALL="ALL")

    def __getattr__(self, _):
        def deco(*a, **k):
            def wrap(fn):
                return fn

            return wrap

        return deco


logging.basicConfig(level=logging.CRITICAL)
_stub(
    "aiohttp",
    ClientSession=object,
    ClientTimeout=lambda *a, **k: None,
    ClientError=Exception,
)
_stub("astrbot", api=types.ModuleType("astrbot.api"))
_stub("astrbot.api", logger=logging.getLogger("t"))
_stub("astrbot.api.event", AstrMessageEvent=object, filter=_Filter())
_stub("astrbot.api.star", Context=object, Star=_Star, register=_register)
_stub("astrbot.core")
_stub("astrbot.core.message")
_stub(
    "astrbot.core.message.components",
    At=object,
    Face=object,
    Image=object,
    Plain=object,
    Record=object,
    Reply=object,
    Video=object,
)
_stub("astrbot.core.star")
_stub("astrbot.core.star.session_llm_manager", SessionServiceManager=object)

spec = importlib.util.spec_from_file_location("face_plugin", MAIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (("  " + detail) if detail and not cond else ""))
    if not cond:
        failures.append(name)


# 与插件里保持一致的请求词守卫
REQ = re.compile(r"重发|再发|再说|再听|再看|发一遍|发一张|换一张|重新发|发个")
HEDGE = mod.FaceConvert.HEDGE_RE


def scrub(text):
    """复刻插件的实际行为：含请求词整条放行，否则过 HEDGE_RE。"""
    return text if REQ.search(text) else HEDGE.sub("", text)


# 1) 真实识别失败请求：必须原样保留（审阅案例，不许再误删）
for s in (
    "我看不清，你能重发一张吗？",
    "这段录音没听清，请再说一次。",
    "没听清，能再说一遍吗？",
):
    check("keep: " + s, scrub(s) == s, repr(scrub(s)))

# 2) 回声型小尾巴：应被擦掉
for s, want in (
    ("看不太清诶", ""),
    ("模模糊糊的", ""),
    ("隐约飘进来一句：你好", "你好"),
):
    got = scrub(s)
    check("strip: " + s, got == want, repr(got))

# 3) 不跨逗号吃下一句
got = scrub("昨天的事模模糊糊的，今天想起来了")
check("cross-clause", "今天想起来了" in got and "模模糊糊" not in got, repr(got))

# 4) file:// 路径三种形态
P = mod.file_uri_to_path
check("path win", P("file:///C:/a/b.mp3") == "C:/a/b.mp3", P("file:///C:/a/b.mp3"))
check("path linux", P("file:///tmp/a.mp3") == "/tmp/a.mp3", P("file:///tmp/a.mp3"))
check("path http", P("https://x/y.mp3") == "https://x/y.mp3", P("https://x/y.mp3"))

# 5) 中文标点归一：顿号当逗号用 / 角括号引号
NORM = mod.FaceConvert._normalize_punctuation
for src, want in (
    # 分句连接词：必须改成逗号
    ("视频本身我这边没声音、也只看得到画面。", "视频本身我这边没声音，也只看得到画面。"),
    ("真通了、也能把那条视频点开。", "真通了，也能把那条视频点开。"),
    ("你喊我、或者该去看看的时候。", "你喊我，或者该去看看的时候。"),
    # 没有连接词的长分句：宁可不动，避免误伤并列名词
    ("浏览器超时、虚拟手机也连不上。", "浏览器超时、虚拟手机也连不上。"),
    ("标题吹得响、封面花里胡哨。", "标题吹得响、封面花里胡哨。"),
    # 并列短词 / 数据列表：保持顿号
    ("直播、推荐、热门、动画、影视频道", "直播、推荐、热门、动画、影视频道"),
    ("2.7 万播放、85 条弹幕、524 赞、183 收藏", "2.7 万播放、85 条弹幕、524 赞、183 收藏"),
    ("31.5 万播放、22 分钟", "31.5 万播放、22 分钟"),
    ("标题、UP 主、链接都带上", "标题、UP 主、链接都带上"),
    ("地点：北京、上海", "地点：北京、上海"),
    # 引号统一
    ("搜「大肥鱼」，弹幕刷「拿 Token 养赛博宠物」。", "搜“大肥鱼”，弹幕刷“拿 Token 养赛博宠物”。"),
    # 代码块原样保留
    ("```python\nprint('a、b')\n```", "```python\nprint('a、b')\n```"),
):
    got = NORM(src)
    check("punct: " + src, got == want, repr(got))

# 6) 身份标记：主人、女主人按平台认；私聊里不标他们，群里标「主人」「女主人」，其他人照旧
import asyncio  # noqa: E402


class _Event:
    def __init__(self, platform, sid, group="", name="小明", text="在吗"):
        self.platform, self.sid, self.group, self.name, self.message_str = platform, sid, group, name, text
        self.extra, self.is_wake = {}, False

    def get_messages(self): return []
    def get_platform_id(self): return self.platform
    def get_sender_id(self): return self.sid
    def get_group_id(self): return self.group
    def get_sender_name(self): return self.name
    def is_private_chat(self): return not self.group
    def get_self_id(self): return "999"
    def get_extra(self, k, default=None): return self.extra.get(k, default)
    def set_extra(self, k, v): self.extra[k] = v


plugin = object.__new__(mod.FaceConvert)
plugin.cfg, plugin.id2name, plugin.admins = dict(mod.DEFAULT_CONFIG), {}, ["astrbot"]
plugin.owner_ids, plugin.partner_ids = {"default:111", "wechat:222"}, {"default:333"}


def tag(platform, sid, group=""):
    ev = _Event(platform, sid, group)
    asyncio.run(plugin.inbound_face_to_text(ev))
    return ev.message_str


for name, args, want in (
    ("QQ 私聊主人小号不标", ("default", "111"), "在吗"),
    ("微信私聊主人不标", ("wechat", "222"), "在吗"),
    ("QQ 私聊女主人不标", ("default", "333"), "在吗"),
    ("QQ 群里主人标主人", ("default", "111", "g1"), "[主人(111)] 在吗"),
    ("微信群里主人标主人", ("wechat", "222", "g1"), "[主人(222)] 在吗"),
    ("QQ 群里女主人标女主人", ("default", "333", "g1"), "[女主人(333)] 在吗"),
    ("微信的号在 QQ 上不算主人", ("default", "222"), "[主人的朋友 小明(222)] 在吗"),
    ("别人私聊照旧", ("wechat", "444"), "[主人的朋友 小明(444)] 在吗"),
    ("别人在群里照旧", ("default", "444", "g1"), "[小明(444)] 在吗"),
):
    got = tag(*args)
    check("tag: " + name, got == want, repr(got))
plugin.admins = ["555"]
check("tag: admins_id 仍算主人", tag("wechat", "555", "g1") == "[主人(555)] 在吗", tag("wechat", "555", "g1"))

print()
if failures:
    print("结果：%d 项失败" % len(failures))
    sys.exit(1)
print("结果：全部通过 OK")
