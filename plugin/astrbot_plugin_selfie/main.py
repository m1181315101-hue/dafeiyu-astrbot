import json
import os
from collections import deque

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from . import album

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


@register(
    "astrbot_plugin_selfie",
    "dafeiyu-local",
    "给她一个 send_selfie 工具：有人要看她的自拍、生活照、和同事的合照时，从她的相册里挑最贴的一张原样发出去",
    "1.1.0",
)
class SelfiePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 照片放在 data/plugin_data/astrbot_plugin_selfie/photos/，往里加图、改 photos.json 都不用重启；
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
        # 每个会话最近发过的几张，下次尽量换
        self.recent: dict[str, deque] = {}
        photos, problem = album.load(self.photo_dir)
        logger.info(f"[selfie] 照片文件夹 {self.photo_dir}，现有 {len(photos)} 张")
        if problem:
            logger.warning(f"[selfie] {problem}，先全当普通自拍")

    @filter.llm_tool(name="send_selfie")
    async def send_selfie(self, event: AstrMessageEvent, kind: str = "", with_whom: str = "", scene: str = ""):
        """发照片：有人想看你的自拍、照片、生活照、你和同事的合照，或者问你长什么样、问哪位同事长什么样时调用。会从你的相册里挑最贴的一张，原样发到当前聊天。

        Args:
            kind(string): 想要哪种：自拍、生活照、合照；对方没说就留空
            with_whom(string): 想看和哪位同事的合照就填她的名字：Claude、GPT、Gemini、Grok、GLM、Kimi、千问，想看大家一起的就填“大家”；不是就留空
            scene(string): 正在聊的场景或对方想看的内容，比如 吃饭、下雨、晚安、过年、万圣节；没有就留空
        """
        photos, problem = album.load(self.photo_dir)
        if problem:
            logger.warning(f"[selfie] {problem}，先全当普通自拍")
        if not photos:
            return "你现在一张照片都没有。用一句话跟对方说现在没有能发的照片，不要假装发了。"
        key = event.unified_msg_origin
        recent = self.recent.setdefault(key, deque(maxlen=5))
        photo, why = album.pick(photos, kind, with_whom, scene, list(recent))
        if photo is None:
            return f"{why}用一句话跟对方说没有，不要假装发了。"
        try:
            await event.send(MessageChain([Image.fromFileSystem(photo["path"])]))
        except Exception as e:
            logger.warning(f"[selfie] 发送失败：{e}")
            return "照片没发出去。用一句话跟对方说刚才没发成功，不要假装发了。"
        recent.append(photo["file"])
        logger.info(f"[selfie] 已发{photo['kind']} {photo['file']} → {key}")
        if not photo["scene"]:
            return "照片已经发出去了。再配一句很短的话就行，不要描述照片里的细节，也不要说自己没有照片。"
        who = f"（和{'、'.join(photo['with'])}的合照）" if photo["with"] else ""
        return (f"照片已经发出去了，是这张：{photo['scene']}{who}。再配一句很短的话，可以顺着这张照片说，"
                "不要编照片里没有的东西，也不要说自己没有照片。")
