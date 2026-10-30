# -*- coding: utf-8 -*-
"""新人欢迎（大肥鱼工具箱 welcome 模块）测试：只认配置里的群、小号自己进群不欢迎、短时间进好几个人合成一句、每天限次、@ 新人。

跑法（纯标准库，不需要 AstrBot 环境）：
    python tests/test_welcome.py
原理：用空壳模块把 astrbot 依赖桩掉，直接加载插件源码，测纯逻辑。
"""
import asyncio
import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "plugin", "astrbot_plugin_dafeiyu", "modules", "welcome.py")


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


class _Comp:
    def __init__(self, **k):
        self.__dict__.update(k)


class _At(_Comp):
    pass


class _Plain(_Comp):
    def __init__(self, text="", **k):  # 和 AstrBot 的 Plain 一样，文字可以直接传
        super().__init__(text=text, **k)


_stub("astrbot")
_stub("astrbot.api", logger=types.SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))
_stub("astrbot.api.event", AstrMessageEvent=object, filter=_Filter())
_stub("astrbot.api.message_components", At=_At, Plain=_Plain)
_stub("astrbot.api.star", Context=object, Star=_Star, register=lambda *a, **k: (lambda c: c))
spec = importlib.util.spec_from_file_location("welcome_main", MAIN)
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)


class Bot:
    def __init__(self, names):
        self.names, self.calls = names, 0

    async def call_action(self, action, **kw):
        self.calls += 1
        return {"card": self.names.get(str(kw["user_id"]), ""), "nickname": ""}


class Mgr:
    async def get_curr_conversation_id(self, umo):
        return "cid1"

    async def get_conversation(self, umo, cid):
        return f"conv:{umo}:{cid}"


class Event:
    def __init__(self, platform, gid, uid, nickname="", operator=0, self_id="999", bot=None):
        raw = {"post_type": "notice", "notice_type": "group_increase", "group_id": gid, "user_id": uid,
               "operator_id": operator, "self_id": self_id}
        if nickname:
            raw["nickname"] = nickname
        self.message_obj = types.SimpleNamespace(raw_message=raw)
        self.platform, self.extra, self.bot = platform, {}, bot
        self.unified_msg_origin = f"{platform}:GroupMessage:{gid}"
        self.result = None

    def get_platform_id(self):
        return self.platform

    def get_self_id(self):
        return "999"

    def set_extra(self, k, v):
        self.extra[k] = v

    def get_extra(self, k):
        return self.extra.get(k)

    def request_llm(self, prompt, conversation=None):
        return {"prompt": prompt, "conversation": conversation}

    def get_result(self):
        return self.result


def plugin(**cfg):
    p = wm.Welcome.__new__(wm.Welcome)
    p.cfg = {**wm.DEFAULTS, "merge_seconds": 0.05, **cfg}
    p.cfg["groups"] = set(p.cfg["groups"])
    p.pending, p.done = {}, {}
    p.context = types.SimpleNamespace(conversation_manager=Mgr())
    return p


async def run(p, event):
    return [x async for x in p.on_group_increase(event)]


failed = 0


def check(name, cond):
    global failed
    print(("  ok  " if cond else "  FAIL ") + name)
    if not cond:
        failed += 1


async def main():
    p = plugin(groups=["wechat:100", "200"])
    check("没开的群不欢迎", await run(p, Event("wechat", 300, 1, "小红")) == [])
    check("小号自己进群不欢迎", await run(p, Event("wechat", 100, 999, "小号")) == [])
    notice = Event("wechat", 100, 1, "小红")
    notice.message_obj.raw_message["notice_type"] = "group_decrease"
    check("不是入群通知不管", await run(p, notice) == [])

    e1, e2 = Event("wechat", 100, 1, "小红", operator=5), Event("wechat", 100, 2, "小明", operator=5,
                                                                    bot=Bot({"5": "老王"}))
    e1.bot = e2.bot
    r1, r2 = await asyncio.gather(run(p, e1), run(p, e2))
    reqs = r1 + r2
    check("同一时间进两个人：只欢迎一次", len(reqs) == 1)
    check("两个名字都在提示里，还说了谁拉进来的", reqs and "小红、小明" in reqs[0]["prompt"] and "老王拉进来的" in reqs[0]["prompt"]
          and "2个新人" in reqs[0]["prompt"])
    check("在这个群当前的对话里请求（人格和上下文照常）", reqs and reqs[0]["conversation"] == "conv:wechat:GroupMessage:100:cid1")
    check("要 @ 的是这两个人", e1.get_extra("_welcome_at") == ["1", "2"])

    qq = Event("default", 200, 7, bot=Bot({"7": "群名片小李"}))
    r = await run(p, qq)
    check("只写群号的配置对 QQ 也生效；QQ 的名字从群名片取", r and "群名片小李" in r[0]["prompt"] and "拉进来" not in r[0]["prompt"])

    p2 = plugin(groups=["wechat:100"], daily_limit=1)
    check("每天限次：第一次欢迎", len(await run(p2, Event("wechat", 100, 1, "甲"))) == 1)
    check("每天限次：第二次不欢迎", await run(p2, Event("wechat", 100, 2, "乙")) == [])

    p3 = plugin(groups=["wechat:100"], at_newcomer=False)
    e = Event("wechat", 100, 1, "甲")
    await run(p3, e)
    check("关了 @ 就不记要 @ 的人", e.get_extra("_welcome_at") is None)

    e = Event("wechat", 100, 1, "甲")
    e.extra["_welcome_at"] = ["1", "2"]
    e.result = types.SimpleNamespace(chain=[_Plain(text="欢迎欢迎")])
    await p.add_at(e)
    chain = e.result.chain
    check("欢迎词前面加上 @", [type(c).__name__ for c in chain] == ["_At", "_At", "_Plain", "_Plain"]
          and chain[0].qq == "1" and chain[3].text == "欢迎欢迎")
    other = Event("wechat", 100, 1, "甲")
    other.result = types.SimpleNamespace(chain=[_Plain(text="普通回复")])
    await p.add_at(other)
    check("普通回复不加 @", len(other.result.chain) == 1)


asyncio.run(main())
print("失败 %d 项" % failed if failed else "全部通过")
sys.exit(1 if failed else 0)
