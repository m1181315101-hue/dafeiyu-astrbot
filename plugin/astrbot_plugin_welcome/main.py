"""新人进群：让她用自己的口吻欢迎一句，@ 新人；只在 config.json 的 groups 里列出的群

入群通知（OneBot 的 group_increase）：QQ 由 NapCat 发，微信由微信连接器（0.11.0 起）发，AstrBot 把它当成一条空的群消息交给插件。
这里不自己拼欢迎词，而是在这个群当前的对话里发起一次 LLM 请求：人格、群聊上下文、表情转换、表情包都照常生效。
短时间里进来好几个人（merge_seconds 内）合成一句；每个群每天最多欢迎 daily_limit 次。
"""
import asyncio
import json
import os
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT = ("[群里有新人] 群里刚进来{count}个新人：{names}{inviter}。用你平时在群里说话的口气欢迎一下，一两句就够，"
                  "带点你自己的风格就行；别长篇大论，别列群规，也别说自己是来欢迎新人的机器人。")
DEFAULTS = {
    "groups": [],          # 开欢迎的群：「平台ID:群号」，QQ 平台 ID 一般是 default，微信是 wechat；只写群号就不分平台
    "merge_seconds": 20,   # 这么多秒里进来的人合成一句
    "at_newcomer": True,   # 欢迎时 @ 新人
    "daily_limit": 10,     # 每个群每天最多欢迎几次
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
    cfg["groups"] = {str(g).strip() for g in cfg["groups"] if str(g).strip()}
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
    "astrbot_plugin_welcome",
    "dafeiyu-local",
    "新人进群时让她用自己的口吻欢迎一句并 @ 新人（只在设置里列出的群）",
    "1.0.0",
)
class WelcomePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.cfg = load_config()
        self.pending: dict[str, list[tuple[str, str, str]]] = {}  # 群 → 等着一起欢迎的 [(OneBot 号, 名字, 邀请人号)]
        self.done: dict[str, list] = {}  # 群 → [日期, 今天欢迎了几次]
        logger.info(f"[welcome] 开欢迎的群 {len(self.cfg['groups'])} 个")

    def _enabled(self, platform: str, gid: str) -> str:
        key = f"{platform}:{gid}"
        return key if key in self.cfg["groups"] or gid in self.cfg["groups"] else ""

    def _take_quota(self, key: str) -> bool:
        today = time.strftime("%Y-%m-%d")
        day, n = self.done.get(key, [today, 0])
        if day != today:
            n = 0
        if n >= int(self.cfg["daily_limit"]):
            return False
        self.done[key] = [today, n + 1]
        return True

    async def _name(self, event: AstrMessageEvent, gid: str, uid: str, raw_name: str = "") -> str:
        """微信连接器在通知里带了昵称；QQ 的要问 NapCat 要群名片或昵称"""
        if raw_name:
            return raw_name
        bot = getattr(event, "bot", None)
        if bot is None:
            return ""
        try:
            info = await bot.call_action("get_group_member_info", group_id=int(gid), user_id=int(uid), no_cache=True)
            return str(info.get("card") or info.get("nickname") or "")
        except Exception:
            return ""

    async def _conversation(self, event: AstrMessageEvent):
        mgr = self.context.conversation_manager
        umo = event.unified_msg_origin
        cid = await mgr.get_curr_conversation_id(umo) or await mgr.new_conversation(umo, event.get_platform_id())
        return await mgr.get_conversation(umo, cid)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_increase(self, event: AstrMessageEvent):
        raw = raw_payload(event)
        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
            return
        gid, uid = str(raw.get("group_id") or ""), str(raw.get("user_id") or "")
        if not gid or not uid or uid == str(raw.get("self_id") or event.get_self_id()):
            return  # 小号自己进群不欢迎
        key = self._enabled(event.get_platform_id(), gid)
        if not key:
            return
        name = await self._name(event, gid, uid, str(raw.get("nickname") or ""))
        operator = str(raw.get("operator_id") or "")
        bucket = self.pending.setdefault(key, [])
        bucket.append((uid, name, operator if operator not in ("", "0", uid) else ""))
        if len(bucket) > 1:
            return  # 前面那个人的欢迎还在等，合进那一句
        await asyncio.sleep(float(self.cfg["merge_seconds"]))
        people = self.pending.pop(key, [])
        if not people:
            return
        if not self._take_quota(key):
            logger.info(f"[welcome] {key} 今天已经欢迎了 {self.cfg['daily_limit']} 次，这次不欢迎（{len(people)} 人）")
            return
        names = "、".join(n or "新朋友" for _, n, _ in people)
        inviters = {o for _, _, o in people if o}
        inviter = ""
        if len(inviters) == 1:
            who = await self._name(event, gid, next(iter(inviters)))
            inviter = f"（{who}拉进来的）" if who else ""
        prompt = self.cfg["prompt"].format(count=len(people), names=names, inviter=inviter)
        if self.cfg["at_newcomer"]:
            event.set_extra("_welcome_at", [u for u, _, _ in people])
        logger.info(f"[welcome] {key} 欢迎 {len(people)} 个新人")
        yield event.request_llm(prompt=prompt, conversation=await self._conversation(event))

    @filter.on_decorating_result()
    async def add_at(self, event: AstrMessageEvent):
        """欢迎词前面 @ 新人"""
        ats = event.get_extra("_welcome_at")
        if not ats:
            return
        event.set_extra("_welcome_at", None)
        result = event.get_result()
        if result is None or not result.chain:
            return
        result.chain[0:0] = [At(qq=u) for u in ats] + [Plain(" ")]
