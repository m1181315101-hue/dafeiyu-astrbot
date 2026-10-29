"""拍一拍 / 戳一戳：有人拍她（微信）或戳她（QQ）时，让她用自己的口吻回一句；只在 config.json 的 platforms 里列出的平台

戳一戳通知（OneBot 的 notice / notify / poke）：QQ 由 NapCat 发，微信由微信连接器（0.12.0 起）把拍一拍转成同样的通知。
AstrBot 把它当成一条空消息交给插件，自己不会回。这里在当前会话的对话里发起一次 LLM 请求：人格、上下文、表情转换、表情包都照常生效。
同一个人连着拍（cooldown_seconds 内）只回第一下；每个会话每天最多回 daily_limit 次。
"""
import json
import os
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT = ("[拍一拍] {name}拍了拍你{suffix}。像平时那样回一句就行，很短，可以嫌弃、撒娇或者接梗；"
                  "别解释拍一拍是什么，也别说自己是机器人。")
DEFAULTS = {
    "platforms": ["wechat"],  # 回哪些平台的：微信是 wechat，QQ 一般是 default
    "cooldown_seconds": 60,   # 同一个人在这么多秒里连着拍，只回第一下
    "daily_limit": 20,        # 每个会话（群或私聊）每天最多回几次
    "prompt": DEFAULT_PROMPT,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            cfg.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    cfg["platforms"] = {str(p).strip() for p in cfg["platforms"] if str(p).strip()}
    return cfg


def raw_payload(event: AstrMessageEvent) -> dict:
    raw = getattr(event.message_obj, "raw_message", None)
    if isinstance(raw, dict):
        return raw
    try:
        return dict(raw)
    except Exception:
        return {}


@register(
    "astrbot_plugin_pat",
    "dafeiyu-local",
    "有人拍一拍（微信）或戳一戳（QQ）她时，用她自己的口吻回一句（只在设置里列出的平台）",
    "1.0.0",
)
class PatPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.cfg = load_config()
        self.last: dict[str, float] = {}  # 会话:人 → 上次拍的时间（回没回都记，连着拍就一直不回）
        self.done: dict[str, list] = {}   # 会话 → [日期, 今天回了几次]
        logger.info(f"[pat] 回拍一拍的平台：{sorted(self.cfg['platforms'])}")

    def _take_quota(self, key: str) -> bool:
        today = time.strftime("%Y-%m-%d")
        day, n = self.done.get(key, [today, 0])
        if day != today:
            n = 0
        if n >= int(self.cfg["daily_limit"]):
            return False
        self.done[key] = [today, n + 1]
        return True

    async def _name(self, event: AstrMessageEvent, raw: dict, uid: str) -> str:
        """微信连接器在通知里带了昵称；QQ 的要问 NapCat 要群名片或昵称"""
        if raw.get("nickname"):
            return str(raw["nickname"])
        bot = getattr(event, "bot", None)
        if bot is None:
            return ""
        try:
            if raw.get("group_id"):
                info = await bot.call_action("get_group_member_info", group_id=int(raw["group_id"]),
                                             user_id=int(uid), no_cache=True)
                return str(info.get("card") or info.get("nickname") or "")
            info = await bot.call_action("get_stranger_info", user_id=int(uid))
            return str(info.get("nickname") or "")
        except Exception:
            return ""

    async def _conversation(self, event: AstrMessageEvent):
        mgr = self.context.conversation_manager
        umo = event.unified_msg_origin
        cid = await mgr.get_curr_conversation_id(umo) or await mgr.new_conversation(umo, event.get_platform_id())
        return await mgr.get_conversation(umo, cid)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_poke(self, event: AstrMessageEvent):
        raw = raw_payload(event)
        if raw.get("post_type") != "notice" or raw.get("notice_type") != "notify" or raw.get("sub_type") != "poke":
            return
        self_id = str(raw.get("self_id") or event.get_self_id())
        uid = str(raw.get("user_id") or "")
        if not uid or uid == self_id or str(raw.get("target_id") or "") != self_id:
            return  # 只管别人戳她；她戳别人、别人之间互戳不管
        if event.get_platform_id() not in self.cfg["platforms"]:
            return
        umo = event.unified_msg_origin
        now = time.time()
        last = self.last.get(f"{umo}:{uid}", 0.0)
        self.last[f"{umo}:{uid}"] = now
        if now - last < float(self.cfg["cooldown_seconds"]):
            return
        if not self._take_quota(umo):
            logger.info(f"[pat] {umo} 今天已经回了 {self.cfg['daily_limit']} 次拍一拍，这次不回")
            return
        name = await self._name(event, raw, uid) or "有人"
        suffix = str(raw.get("suffix") or "")
        prompt = self.cfg["prompt"].format(name=name, suffix=suffix)
        logger.info(f"[pat] {umo} 有人拍了拍她")
        yield event.request_llm(prompt=prompt, conversation=await self._conversation(event))
