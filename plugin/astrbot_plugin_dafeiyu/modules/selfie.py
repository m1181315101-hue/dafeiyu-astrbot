"""发照片：send_selfie 工具（原 astrbot_plugin_selfie 1.1.0）。

搬进大肥鱼工具箱时只改了配置读取（从工具箱的「selfie」一节读）；照片默认还放在原来的
data/plugin_data/astrbot_plugin_selfie/photos/，不用挪。工具说明还在 main.py 的 send_selfie 上。
1.3.0 起：最近发过的 recent_count 张尽量不重复；daily_limit 设了的话每个聊天每天最多发这么多张（默认 0 不限），
到了让她自己说今天发够了。这两样按聊天记在 data/plugin_data/astrbot_plugin_selfie/sent.json，重启不丢。
"""
import datetime
import json
import os

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Image
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from . import album

ENOUGH_TODAY = ("今天在这个聊天里已经发过好几张照片了，这次先不发。用你自己的口气说一句今天发够了、明天再看，"
                "可以嫌弃两句或撒个娇，别真发，也别提什么次数限制。")


class Selfie:
    def __init__(self, cfg: dict):
        # 照片放在 data/plugin_data/astrbot_plugin_selfie/photos/，往里加图、改 photos.json 都不用重启；
        # 工具箱「selfie」一节的 photo_dir 可以换个文件夹
        self.photo_dir = os.path.join(get_astrbot_data_path(), "plugin_data", "astrbot_plugin_selfie", "photos")
        loaded = cfg
        if isinstance(loaded, dict) and str(loaded.get("photo_dir", "")).strip():
            self.photo_dir = str(loaded["photo_dir"]).strip()
        os.makedirs(self.photo_dir, exist_ok=True)
        self.daily_limit = max(0, int(loaded.get("daily_limit", 0)))
        self.recent_count = max(1, int(loaded.get("recent_count", 10)))
        # 每个聊天：{"date": 今天, "count": 今天发了几张, "recent": 最近发过的文件名}
        self.state_path = os.path.join(get_astrbot_data_path(), "plugin_data", "astrbot_plugin_selfie", "sent.json")
        self.state = self._load_state()
        photos, problem = album.load(self.photo_dir)
        logger.info(f"[selfie] 照片文件夹 {self.photo_dir}，现有 {len(photos)} 张")
        if problem:
            logger.warning(f"[selfie] {problem}，先全当普通自拍")

    def _load_state(self) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:  # noqa: BLE001 - 记录坏了就从头记，不影响发照片
            logger.warning(f"[selfie] 发送记录读不了，从头记：{e}")
            return {}

    def _save_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False)
            os.replace(tmp, self.state_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[selfie] 发送记录没存上：{e}")

    async def send_selfie(self, event: AstrMessageEvent, kind: str = "", with_whom: str = "", scene: str = ""):
        photos, problem = album.load(self.photo_dir)
        if problem:
            logger.warning(f"[selfie] {problem}，先全当普通自拍")
        if not photos:
            return "你现在一张照片都没有。用一句话跟对方说现在没有能发的照片，不要假装发了。"
        key = event.unified_msg_origin
        entry = self.state.setdefault(key, {})
        today = datetime.datetime.now(album.TZ).date().isoformat()
        if entry.get("date") != today:
            entry["date"], entry["count"] = today, 0
        if self.daily_limit and entry.get("count", 0) >= self.daily_limit:
            logger.info(f"[selfie] {key} 今天已经发了 {entry['count']} 张，这次不发")
            return ENOUGH_TODAY
        recent = [f for f in entry.get("recent", []) if isinstance(f, str)][-self.recent_count:]
        photo, why = album.pick(photos, kind, with_whom, scene, recent)
        if photo is None:
            return f"{why}用一句话跟对方说没有，不要假装发了。"
        try:
            await event.send(MessageChain([Image.fromFileSystem(photo["path"])]))
        except Exception as e:
            logger.warning(f"[selfie] 发送失败：{e}")
            return "照片没发出去。用一句话跟对方说刚才没发成功，不要假装发了。"
        entry["recent"] = (recent + [photo["file"]])[-self.recent_count:]
        entry["count"] = entry.get("count", 0) + 1
        self._save_state()
        logger.info(f"[selfie] 已发{photo['kind']} {photo['file']} → {key}（今天第 {entry['count']} 张）")
        if not photo["scene"]:
            return "照片已经发出去了。再配一句很短的话就行，不要描述照片里的细节，也不要说自己没有照片。"
        who = f"（和{'、'.join(photo['with'])}的合照）" if photo["with"] else ""
        return (f"照片已经发出去了，是这张：{photo['scene']}{who}。再配一句很短的话，可以顺着这张照片说，"
                "不要编照片里没有的东西，也不要说自己没有照片。")
