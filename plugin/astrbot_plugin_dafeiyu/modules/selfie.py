"""发照片：send_selfie 工具（原 astrbot_plugin_selfie 1.1.0）。

搬进大肥鱼工具箱时只改了配置读取（从工具箱的「selfie」一节读）；照片默认还放在原来的
data/plugin_data/astrbot_plugin_selfie/photos/，不用挪。工具说明还在 main.py 的 send_selfie 上。
"""
import os
from collections import deque

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Image
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from . import album


class Selfie:
    def __init__(self, cfg: dict):
        # 照片放在 data/plugin_data/astrbot_plugin_selfie/photos/，往里加图、改 photos.json 都不用重启；
        # 工具箱「selfie」一节的 photo_dir 可以换个文件夹
        self.photo_dir = os.path.join(get_astrbot_data_path(), "plugin_data", "astrbot_plugin_selfie", "photos")
        loaded = cfg
        if isinstance(loaded, dict) and str(loaded.get("photo_dir", "")).strip():
            self.photo_dir = str(loaded["photo_dir"]).strip()
        os.makedirs(self.photo_dir, exist_ok=True)
        # 每个会话最近发过的几张，下次尽量换
        self.recent: dict[str, deque] = {}
        photos, problem = album.load(self.photo_dir)
        logger.info(f"[selfie] 照片文件夹 {self.photo_dir}，现有 {len(photos)} 张")
        if problem:
            logger.warning(f"[selfie] {problem}，先全当普通自拍")

    async def send_selfie(self, event: AstrMessageEvent, kind: str = "", with_whom: str = "", scene: str = ""):
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
