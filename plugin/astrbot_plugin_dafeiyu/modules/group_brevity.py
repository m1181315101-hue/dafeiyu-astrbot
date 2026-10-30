"""群里说得短就回得短：群里叫她的这句只有几个字时，请求模型前给这一轮加一句提醒，让她一条消息接住就行。

统计（2026-10-30，她约 1700 条回复）：私聊里对方发 5 字以内，她回中位 13 字、12% 拆成多条；
群里同样 5 字以内，她回中位 22 字、39% 拆成多条，86% 比对方长 3 倍以上。人格里「群里回得简短」管不住，
这里按这一句的实际长度提醒。提醒只发给模型、不存进聊天历史（mark_as_temp），不动系统提示词。
"""
import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Plain

FACE = re.compile(r"\[[^\[\]]{1,8}\]")


class GroupBrevity:
    def __init__(self, cfg: dict):
        # 工具箱「group_brevity」一节：{"short_chars": 15}
        self.short_chars = max(1, int(cfg.get("short_chars", 15)))
        logger.info(f"[group_brevity] 群里叫她的话不超过 {self.short_chars} 个字时，提醒她一条接住")

    @staticmethod
    def spoken_length(event: AstrMessageEvent) -> int:
        """这句自己说了几个字：只数文字段，不算 @、引用、表情标记和空白"""
        text = "".join(c.text for c in event.get_messages() if isinstance(c, Plain) and c.text)
        return len(re.sub(r"\s+", "", FACE.sub("", text)))

    def hint_for(self, event: AstrMessageEvent) -> str:
        # 只管群里有人叫她的这一轮；陪伴插件自己发起的主动消息不算，只发图、表情的也不管
        if not event.get_group_id() or not event.is_at_or_wake_command:
            return ""
        if getattr(event, "private_companion_proactive_framework", False):
            return ""
        n = self.spoken_length(event)
        if not 0 < n <= self.short_chars:
            return ""
        return (f"【回短点】对方这句就 {n} 个字：一条消息接住就行，别拆成好几条，也别铺垫、别总结；"
                "要查东西、发图就照常做，说结论用一两句。")

    async def add_hint(self, event: AstrMessageEvent, req) -> bool:
        """main.py 在 on_llm_request 接上"""
        hint = self.hint_for(event)
        if not hint:
            return False
        if not isinstance(getattr(req, "extra_user_content_parts", None), list):
            req.extra_user_content_parts = []
        req.extra_user_content_parts.append(TextPart(text=hint).mark_as_temp())
        return True
