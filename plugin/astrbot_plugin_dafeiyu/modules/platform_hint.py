# -*- coding: utf-8 -*-
"""告诉她这条消息来自哪个平台（QQ 还是微信）。

AstrBot 给模型的发送者信息只有 User ID 和昵称，不分平台，接上微信以后她会在微信里说自己在 QQ，
认主人时也分不清一个 User ID 是 QQ 号还是微信连接器的号。这里按事件的平台 ID 在系统提示词末尾加一行：
- 平台 ID → 名字的对照在工具箱「platform_hint」一节的 platforms 里，一行一个「平台ID=名字」
  （默认 wechat=微信、webchat=网页面板），没列出的按 default_name（默认 QQ）；
- 人格里再写清楚：说自己在哪按【当前平台】来，认主人时 User ID 要和平台对上。

原 astrbot_plugin_platform_hint 1.0.0，搬进大肥鱼工具箱时只改了配置读取：面板没有「对照表」类型的配置，
platforms 改成一行一个「平台ID=名字」的列表，这里再拆回对照表。
"""
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

MARKER = "【当前平台】"
DEFAULTS = {"platforms": {"wechat": "微信", "webchat": "网页面板"}, "default_name": "QQ"}


def parse_platforms(lines) -> dict:
    """["wechat=微信", "webchat=网页面板"] → {"wechat": "微信", "webchat": "网页面板"}；写坏的行跳过"""
    out = {}
    for line in lines or []:
        key, sep, name = str(line).partition("=")
        if sep and key.strip() and name.strip():
            out[key.strip()] = name.strip()
    return out


class PlatformHint:
    def __init__(self, cfg: dict):
        self.cfg = dict(DEFAULTS)
        if isinstance(cfg, dict):
            if isinstance(cfg.get("platforms"), list):
                self.cfg["platforms"] = parse_platforms(cfg["platforms"])
            if str(cfg.get("default_name", "")).strip():
                self.cfg["default_name"] = str(cfg["default_name"]).strip()

    async def inject_platform(self, event: AstrMessageEvent, req) -> None:
        try:
            name = self.cfg["platforms"].get(event.get_platform_id(), self.cfg["default_name"])
            base = req.system_prompt or ""
            # 同一请求被重复处理时只留一行
            cut = base.find(MARKER)
            if cut != -1:
                end = base.find("\n", cut)
                base = base[:cut] + (base[end + 1:] if end != -1 else "")
            req.system_prompt = (base.rstrip() + f"\n\n{MARKER}这条消息来自{name}。").strip()
        except Exception as exc:  # noqa: BLE001 - 注入失败不能影响聊天
            logger.warning(f"[platform_hint] 标平台失败: {exc}")
