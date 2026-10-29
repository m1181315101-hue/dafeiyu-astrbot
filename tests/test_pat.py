# -*- coding: utf-8 -*-
"""拍一拍插件测试：只认配置里的平台、只管别人拍她、连着拍只回第一下、每天限次、名字和后缀进提示。

跑法（纯标准库，不需要 AstrBot 环境）：
    python tests/test_pat.py
原理：用空壳模块把 astrbot 依赖桩掉，直接加载插件源码，测纯逻辑。
"""
import asyncio
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "plugin", "astrbot_plugin_pat", "main.py")


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Star:
    def __init__(self, *a, **k):
        pass


class _Filter:
    EventMessageType = types.SimpleNamespace(GROUP_MESSAGE="GROUP", ALL="ALL")

    def __getattr__(self, name):
        return lambda *a, **k: (lambda f: f)


_stub("astrbot")
_stub("astrbot.api", logger=types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))
_stub("astrbot.api.event", AstrMessageEvent=object, filter=_Filter())
_stub("astrbot.api.star", Context=object, Star=_Star, register=lambda *a, **k: (lambda c: c))
spec = importlib.util.spec_from_file_location("pat_main", MAIN)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class Bot:
    def __init__(self, card="", nickname=""):
        self.card, self.nickname, self.calls = card, nickname, []

    async def call_action(self, action, **kw):
        self.calls.append(action)
        return {"card": self.card, "nickname": self.nickname}


class Mgr:
    async def get_curr_conversation_id(self, umo):
        return "cid1"

    async def get_conversation(self, umo, cid):
        return f"conv:{umo}:{cid}"


class Event:
    def __init__(self, platform, uid, gid=None, target="999", nickname="", suffix="", sub_type="poke", bot=None):
        raw = {"post_type": "notice", "notice_type": "notify", "sub_type": sub_type, "user_id": uid,
               "target_id": target, "self_id": "999"}
        if gid:
            raw["group_id"] = gid
        if nickname:
            raw["nickname"] = nickname
        if suffix:
            raw["suffix"] = suffix
        self.message_obj = types.SimpleNamespace(raw_message=raw)
        self.platform, self.bot = platform, bot
        self.unified_msg_origin = f"{platform}:{'GroupMessage' if gid else 'FriendMessage'}:{gid or uid}"

    def get_platform_id(self):
        return self.platform

    def get_self_id(self):
        return "999"

    def request_llm(self, prompt, conversation=None):
        return {"prompt": prompt, "conversation": conversation}


def plugin(**cfg):
    p = pm.PatPlugin.__new__(pm.PatPlugin)
    p.cfg = {**pm.DEFAULTS, **cfg}
    p.cfg["platforms"] = set(p.cfg["platforms"])
    p.last, p.done = {}, {}
    p.context = types.SimpleNamespace(conversation_manager=Mgr())
    return p


async def run(p, event):
    return [x async for x in p.on_poke(event)]


failed = 0


def check(name, cond):
    global failed
    print(("  ok  " if cond else "  FAIL ") + name)
    if not cond:
        failed += 1


async def main():
    p = plugin()
    r = await run(p, Event("wechat", 1, gid=100, nickname="小红", suffix="的小尾巴"))
    check("微信群里有人拍她：在这个群当前的对话里请求一次", len(r) == 1
          and r[0]["conversation"] == "conv:wechat:GroupMessage:100:cid1")
    check("名字和后缀写进提示", r and r[0]["prompt"].startswith("[拍一拍] 小红拍了拍你的小尾巴。"))
    check("同一个人马上又拍：不回", await run(p, Event("wechat", 1, gid=100, nickname="小红")) == [])
    check("别的人拍：照样回", len(await run(p, Event("wechat", 2, gid=100, nickname="小明"))) == 1)
    r = await run(p, Event("wechat", 3, nickname="阿杰"))
    check("私聊拍她也回，没后缀就不带", r and "阿杰拍了拍你。" in r[0]["prompt"]
          and r[0]["conversation"] == "conv:wechat:FriendMessage:3:cid1")
    check("没开的平台（QQ）不回", await run(p, Event("default", 4, gid=200)) == [])
    check("拍的是别人：不回", await run(p, Event("wechat", 5, gid=100, target="6")) == [])
    check("她自己拍别人：不回", await run(p, Event("wechat", 999, gid=100, target="999")) == [])
    check("别的通知（比如头衔变化）：不回", await run(p, Event("wechat", 7, gid=100, sub_type="title")) == [])

    qq = plugin(platforms=["default"])
    bot = Bot(card="群名片小李")
    r = await run(qq, Event("default", 8, gid=200, bot=bot))
    check("QQ 群：名字从群名片取", r and "群名片小李拍了拍你" in r[0]["prompt"] and bot.calls == ["get_group_member_info"])
    bot = Bot(nickname="QQ昵称")
    r = await run(qq, Event("default", 9, bot=bot))
    check("QQ 私聊：名字从陌生人信息取", r and "QQ昵称拍了拍你" in r[0]["prompt"] and bot.calls == ["get_stranger_info"])
    r = await run(qq, Event("default", 10, gid=200))
    check("取不到名字就叫「有人」", r and r[0]["prompt"].startswith("[拍一拍] 有人拍了拍你"))

    limited = plugin(daily_limit=1, cooldown_seconds=0)
    check("每天限次：第一次回", len(await run(limited, Event("wechat", 1, gid=100))) == 1)
    check("每天限次：第二次不回", await run(limited, Event("wechat", 2, gid=100)) == [])

    cool = plugin(cooldown_seconds=0)
    await run(cool, Event("wechat", 1, gid=100))
    check("冷却设成 0：同一个人再拍也回", len(await run(cool, Event("wechat", 1, gid=100))) == 1)


asyncio.run(main())
print("失败 %d 项" % failed if failed else "全部通过")
sys.exit(1 if failed else 0)
