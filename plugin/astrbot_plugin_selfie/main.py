import json
import os
import random

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


@register(
    "astrbot_plugin_selfie",
    "dafeiyu-local",
    "给她一个 send_selfie 工具：有人要看她的自拍、照片时，从她的照片文件夹里挑一张原样发出去",
    "1.0.0",
)
class SelfiePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 照片放在 data/plugin_data/astrbot_plugin_selfie/photos/，往里加图就行，不用重启；
        # 同目录 config.json 的 photo_dir 可以换个文件夹（改完需重启 AstrBot）
        self.photo_dir = os.path.join(get_astrbot_data_path(), "plugin_data", "astrbot_plugin_selfie", "photos")
        try:
            with open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and str(loaded.get("photo_dir", "")).strip():
                self.photo_dir = str(loaded["photo_dir"]).strip()
        except (OSError, ValueError):
            pass
        os.makedirs(self.photo_dir, exist_ok=True)
        # 每个会话上一次发的是哪张，下次尽量换一张
        self.last: dict[str, str] = {}
        logger.info(f"[selfie] 照片文件夹 {self.photo_dir}，现有 {len(self._photos())} 张")

    def _photos(self) -> list[str]:
        try:
            names = sorted(os.listdir(self.photo_dir))
        except OSError:
            return []
        return [os.path.join(self.photo_dir, n) for n in names
                if n.lower().endswith(PHOTO_EXTS) and not n.startswith(".")]

    @filter.llm_tool(name="send_selfie")
    async def send_selfie(self, event: AstrMessageEvent):
        """发自拍：有人想看你的自拍、照片，或者问你长什么样时调用。会从你自己的照片里挑一张，原样发到当前聊天。"""
        photos = self._photos()
        if not photos:
            return "你现在一张自拍都没有。用一句话跟对方说现在没有能发的照片，不要假装发了。"
        key = event.unified_msg_origin
        path = random.choice([p for p in photos if p != self.last.get(key)] or photos)
        try:
            await event.send(MessageChain([Image.fromFileSystem(path)]))
        except Exception as e:
            logger.warning(f"[selfie] 发送失败：{e}")
            return "照片没发出去。用一句话跟对方说刚才没发成功，不要假装发了。"
        self.last[key] = path
        logger.info(f"[selfie] 已发自拍 {os.path.basename(path)} → {key}")
        return "自拍已经发出去了。再配一句很短的话就行，不要描述照片里的细节，也不要说自己没有照片。"
