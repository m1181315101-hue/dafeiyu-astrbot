"""定时任务把关：定时任务跑的时候最多带最近几轮上下文；可以只让主人建定时任务。

- AstrBot 4.29 跑 future_task 建的定时任务时（cron/manager.py），把那个会话存着的整段聊天记录原样放进请求。
  这条路不经过 on_llm_request，陪伴插件平时对群聊上下文的裁剪管不到；模型上下文上限 100 万，AstrBot 也不压缩。
  2026-11-01 量到：一个每半小时跑一次的盯盘任务所在的群存了 985 条、约 29 万字符，每跑一次调四五回模型，
  回回整段带上。这里在 agent 开跑时（on_agent_begin，定时任务也走这个钩子）把上下文截到最多 keep_turns 轮，
  只改这一次请求，存着的记录不动。轮数照 AstrBot 自己的算法（一问一答两条算一轮、从一句用户消息开始），
  中间调工具多的轮占的条数多，实际带的轮数会更少。
- future_task 是 AstrBot 内置工具，面板里的工具权限只管插件和 MCP 工具，管不到它：谁跟她说「每半小时帮我看一下」
  都能建，跑起来花的是主人的 token。owner_only 打开时，在请求模型前（on_llm_request，这时 AstrBot 已经把工具加上了）
  把不是主人的请求里的 future_task 拿掉，再给这一轮加一句提醒，免得她嘴上答应、实际建不了。
  主人：AstrBot 管理员，加上 face 一节「主人的号」（写法一样，「号」或「平台ID:号」）。
"""
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.agent.context.truncator import ContextTruncator
from astrbot.core.agent.message import TextPart

CRON_TOOL = "future_task"
OWNER_ONLY_HINT = ("【定时任务】定时提醒、定时盯盘这类只有主人能设，你自己设不了；"
                   "有人让你定时做事，直说这得找主人，别答应下来。")


class CronGuard:
    def __init__(self, cfg: dict, owner_ids=None, admins=None):
        # 工具箱「cron_guard」一节：{"keep_turns": 8, "owner_only": false}；owner_ids 是 face 一节的「主人的号」
        self.keep_turns = max(0, int(cfg.get("keep_turns", 8)))
        self.owner_only = bool(cfg.get("owner_only", False))
        self.owner_ids = {str(x).strip() for x in (owner_ids or []) if str(x).strip()}
        self.admins = {str(x).strip() for x in (admins or []) if str(x).strip()}
        logger.info(
            f"[cron_guard] 定时任务{f'最多带最近 {self.keep_turns} 轮上下文' if self.keep_turns else '上下文照原样整段带上'}；"
            f"{'只有主人能让她建定时任务' if self.owner_only else '谁都能让她建定时任务'}"
        )

    def trim(self, event: AstrMessageEvent, run_context) -> bool:
        """main.py 在 on_agent_begin 接上；定时任务的事件平台名是 cron"""
        if not self.keep_turns or event.get_platform_name() != "cron":
            return False
        messages = run_context.messages
        kept = ContextTruncator().truncate_by_turns(messages, keep_most_recent_turns=self.keep_turns)
        if len(kept) >= len(messages):
            return False
        run_context.messages = kept
        logger.info(f"[cron_guard] 定时任务最多带最近 {self.keep_turns} 轮：{len(messages)} 条 → {len(kept)} 条")
        return True

    def is_owner(self, event: AstrMessageEvent) -> bool:
        sid = str(event.get_sender_id())
        return (event.is_admin() or sid in self.admins or sid in self.owner_ids
                or f"{event.get_platform_id()}:{sid}" in self.owner_ids)

    async def guard_tool(self, event: AstrMessageEvent, req) -> bool:
        """main.py 在 on_llm_request 接上：不是主人的请求里拿掉 future_task，这一轮加一句提醒（不存进聊天历史）"""
        tools = getattr(req, "func_tool", None)
        if not self.owner_only or tools is None or tools.get_tool(CRON_TOOL) is None or self.is_owner(event):
            return False
        tools.remove_tool(CRON_TOOL)
        if not isinstance(getattr(req, "extra_user_content_parts", None), list):
            req.extra_user_content_parts = []
        req.extra_user_content_parts.append(TextPart(text=OWNER_ONLY_HINT).mark_as_temp())
        return True
