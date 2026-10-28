import json
import os
import re
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import At, AtAll, Plain, Reply

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# 短消息里出现这些词，就当对方在收尾：这条照常回，回完关窗口
BYE_RE = re.compile(r"拜拜|拜了|再见|晚安|88|886|不聊了|先这样|下了|溜了|去忙了|睡了|不说了|回头聊")
FOLLOWUP_HINT = (
    "\n[群聊续聊] 对方这条消息没有 @ 你，是接着刚才和你的对话说的。"
    "如果它看起来是在跟群里别人说话，或者不需要你接话，就只输出 [NO_REPLY]，不要带其他文字。\n"
)


@register(
    "astrbot_plugin_group_followup",
    "dafeiyu-local",
    "群聊续聊：谁 @ 了她，接下来几分钟里这个人不用再 @ 也能接着聊",
    "1.0.0",
)
class GroupFollowupPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 同目录 config.json，改完需重启 AstrBot
        self.window_seconds = 180
        self.max_followups = 8
        try:
            with open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.window_seconds = int(loaded.get("window_seconds", self.window_seconds))
                self.max_followups = int(loaded.get("max_followups", self.max_followups))
        except (OSError, ValueError):
            pass
        # (群号, QQ号) -> {"until": 过期时间戳, "count": 已免 @ 续聊的条数}
        self.windows: dict[tuple[str, str], dict] = {}
        logger.info(f"[group_followup] 续聊窗口 {self.window_seconds} 秒，最多 {self.max_followups} 条")

    @staticmethod
    def _key(event: AstrMessageEvent) -> tuple[str, str]:
        return str(event.get_group_id()), str(event.get_sender_id())

    def _open(self, key: tuple[str, str]) -> None:
        self.windows[key] = {"until": time.time() + self.window_seconds, "count": 0}

    def _close(self, key: tuple[str, str], why: str) -> None:
        if self.windows.pop(key, None) is not None:
            logger.info(f"[group_followup] 结束续聊 {key[0]}/{key[1]}：{why}")

    @staticmethod
    def _talking_to_others(event: AstrMessageEvent) -> bool:
        """@ 了别人，或者引用的是别人的消息"""
        self_id = str(event.get_self_id())
        for comp in event.get_messages():
            if isinstance(comp, At) and str(comp.qq) not in (self_id, "all"):
                return True
            if isinstance(comp, Reply) and str(comp.sender_id) != self_id:
                return True
        return False

    # 排在 private_only（100000）之后：不允许的群已经被它拦掉了
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=99000)
    async def follow_up(self, event: AstrMessageEvent):
        key = self._key(event)
        now = time.time()
        if event.is_at_or_wake_command:
            # @ 她、引用她、喊“大肥鱼”：开新窗口
            self._open(key)
            return
        win = self.windows.get(key)
        if win is None:
            return
        if now > win["until"]:
            self._close(key, "超时没再说话")
            return
        if self._talking_to_others(event):
            self._close(key, "转去跟别人说话了")
            return
        if win["count"] >= self.max_followups:
            self._close(key, f"免 @ 已聊 {self.max_followups} 条，之后要重新 @")
            return
        win["count"] += 1
        event.is_at_or_wake_command = True
        event.set_extra("dafeiyu_followup", True)
        text = event.message_str.strip()
        if len(text) <= 12 and BYE_RE.search(text):
            event.set_extra("dafeiyu_followup_bye", True)

    @filter.on_llm_request()
    async def add_hint(self, event: AstrMessageEvent, req: ProviderRequest):
        if event.get_extra("dafeiyu_followup"):
            req.system_prompt = (req.system_prompt or "") + FOLLOWUP_HINT

    # 比表情插件先执行：它会把 [NO_REPLY] 整条吞掉，吞之前要先看到
    @filter.on_decorating_result(priority=10)
    async def after_reply(self, event: AstrMessageEvent):
        if not event.get_group_id():
            return
        key = self._key(event)
        if key not in self.windows:
            return
        result = event.get_result()
        text = "".join(c.text for c in (result.chain if result else []) if isinstance(c, Plain) and c.text)
        if "[NO_REPLY]" in text.upper():
            self._close(key, "她判断这条不是跟她说的")
        elif event.get_extra("dafeiyu_followup_bye"):
            self._close(key, "对方说了再见")
        else:
            # 每回一次，窗口从现在起重新计时
            self.windows[key]["until"] = time.time() + self.window_seconds
