"""只回私聊：群消息在最前面就终止，不触发指令、插件和 LLM；allowed_groups 里列出的群除外。

原 astrbot_plugin_private_only 1.1.0，搬进大肥鱼工具箱时只改了配置读取（从工具箱的「private_only」一节读）。
"""
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class PrivateOnly:
    def __init__(self, cfg: dict):
        # 工具箱「private_only」一节：{"allowed_groups": ["群号", ...]}
        self.allowed_groups: set[str] = set()
        loaded = cfg
        if isinstance(loaded, dict):
            self.allowed_groups = {str(g).strip() for g in loaded.get("allowed_groups", []) if str(g).strip()}
        logger.info(f"[private_only] 允许回复的群：{sorted(self.allowed_groups) or '无'}")

    # priority 越大越先执行；stop_event() 会带上“已终止”的结果，后续 handler 和 LLM 都不再处理（main.py 按 priority=100000 接上）
    async def drop_group_message(self, event: AstrMessageEvent):
        if str(event.get_group_id()).strip() in self.allowed_groups:
            return
        # 只记被 @ / 唤醒的那些，普通群聊不刷日志
        if event.is_at_or_wake_command:
            logger.info(f"[private_only] 群里有人唤醒她，已忽略：{event.unified_msg_origin}")
        event.stop_event()
