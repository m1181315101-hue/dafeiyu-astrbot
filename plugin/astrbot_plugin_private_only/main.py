import json
import os

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


@register(
    "astrbot_plugin_private_only",
    "dafeiyu-local",
    "只回私聊：群消息在最前面就终止，不触发指令、插件和 LLM；config.json 里列出的群除外",
    "1.1.0",
)
class PrivateOnlyPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 同目录 config.json：{"allowed_groups": ["群号", ...]}，改完需重启 AstrBot
        self.allowed_groups: set[str] = set()
        try:
            with open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.allowed_groups = {str(g).strip() for g in loaded.get("allowed_groups", []) if str(g).strip()}
        except (OSError, ValueError):
            pass
        logger.info(f"[private_only] 允许回复的群：{sorted(self.allowed_groups) or '无'}")

    # priority 越大越先执行；stop_event() 会带上“已终止”的结果，后续 handler 和 LLM 都不再处理
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=100000)
    async def drop_group_message(self, event: AstrMessageEvent):
        if str(event.get_group_id()).strip() in self.allowed_groups:
            return
        # 只记被 @ / 唤醒的那些，普通群聊不刷日志
        if event.is_at_or_wake_command:
            logger.info(f"[private_only] 群里有人唤醒她，已忽略：{event.unified_msg_origin}")
        event.stop_event()
