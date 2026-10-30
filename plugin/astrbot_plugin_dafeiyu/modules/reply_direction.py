"""引用她又 @ 别人：群里有人引用她说过的话、同时 @ 了别人，告诉她这句在跟谁说。

AstrBot 只要看到「引用了她的消息」就算叫到她（waking_check），不管这条另外 @ 了谁；她拿到的只是
「引用：她的话」+「@B(号) 正文」，常把「@B 你看她说的」当成在问自己。这里不拦，她照常可以接话，
只在请求模型前给这一轮加一段说明：谁引用了她、@ 的是谁、这句主要是说给谁听的，让她先读懂再接。
说明只发给模型、不存进聊天历史（mark_as_temp），也不动系统提示词，前面的缓存不受影响。
微信要连接器 0.13.0 起把 @ 名单转成 at 段，这里才认得出 @ 了别人。
"""
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import At, Reply


class ReplyDirection:
    def __init__(self, cfg: dict):
        logger.info("[reply_direction] 引用她又 @ 别人时，告诉她这句在跟谁说")

    @staticmethod
    def hint_for(event: AstrMessageEvent) -> str:
        """这条是「引用她、@ 别人」就返回给她的说明，不是返回空串"""
        self_id = str(event.get_self_id())
        comps = event.get_messages()
        if not any(isinstance(c, Reply) and str(c.sender_id) == self_id for c in comps):
            return ""
        ats = [c for c in comps if isinstance(c, At)]
        others = list(dict.fromkeys(
            (str(c.name or "").strip() or f"号码 {c.qq}") for c in ats if str(c.qq) not in (self_id, "all")
        ))
        if not others:
            return ""
        sender = str(event.get_sender_name() or "").strip() or "对方"
        targets = "、".join(others[:3]) + ("等人" if len(others) > 3 else "")
        if any(str(c.qq) == self_id for c in ats):
            return (f"【这句在跟谁说】{sender}引用了你之前说的话，同时 @ 了你和{targets}："
                    f"这句是对你们说的，回的时候别漏了{targets}。")
        return (f"【这句在跟谁说】{sender}引用了你之前说的话，但 @ 的是{targets}，不是你："
                f"这句主要是说给{targets}听的，你说的那句是话题。你可以接话，但先读懂{sender}的意思"
                f"——是让{targets}看你说的、跟{targets}聊你说的，还是拿你的话打趣——顺着这个意思接，"
                f"别当成{sender}在问你；要回应{targets}就直接对{targets}说。")

    async def add_hint(self, event: AstrMessageEvent, req) -> bool:
        """请求模型前加说明，返回加没加（main.py 在 on_llm_request 接上）"""
        hint = self.hint_for(event)
        if not hint:
            return False
        if not isinstance(getattr(req, "extra_user_content_parts", None), list):
            req.extra_user_content_parts = []
        req.extra_user_content_parts.append(TextPart(text=hint).mark_as_temp())
        logger.info(f"[reply_direction] {event.unified_msg_origin} 有人引用了她的话、@ 的是别人，已告诉她这句在跟谁说")
        return True
