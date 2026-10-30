"""图片复读：群里连着几个人发同一张图（多半是表情包），她也跟一张，像群友那样凑个热闹。

陪伴插件的复读机只认文字，纯图片消息一律当「[图片]」占位跳过；这里补上图片这一半，不调模型。
- 「同一张」：微信连接器给表情包的文件名就是原图 md5（QQ 的图片文件名多半也是），优先认它；
  没有就认去掉参数的下载地址，再没有就认 base64 内容的摘要。
- 要连着 min_people 条都是这张图、来自 min_people 个不同的人；中间插进别的话就重新数。
- 同一串只判一次，按 probability 掷骰；每个群有冷却和每天上限。
- 发的是原图：下载回来按 base64 发，微信连接器照常处理（GIF 默认取中间一帧当图片发）。
"""
import base64
import datetime
import hashlib
import os
import random
import re
import time
from collections import deque

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.message.components import Image, Plain

MAX_BYTES = 5 * 1024 * 1024
TZ = datetime.timezone(datetime.timedelta(hours=8))


class ImageRepeat:
    def __init__(self, cfg: dict):
        # 工具箱「image_repeat」一节
        self.min_people = max(2, int(cfg.get("min_people", 3)))
        self.probability = min(100, max(0, int(cfg.get("probability", 60))))
        self.cooldown = max(0, int(cfg.get("cooldown_minutes", 10))) * 60
        self.daily_limit = max(0, int(cfg.get("daily_limit", 5)))
        self.recent: dict[str, deque] = {}  # 群 → 最近连着的 (图片, 发的人)
        self.decided: dict[str, str] = {}  # 群 → 这一串已经判过的图片
        self.last_sent: dict[str, float] = {}
        self.today: dict[str, tuple[str, int]] = {}  # 群 → (日期, 今天跟了几次)
        logger.info(f"[image_repeat] 群里 {self.min_people} 个人连着发同一张图时，{self.probability}% 跟一张")

    @staticmethod
    def image_of(event: AstrMessageEvent) -> tuple[str, Image | None]:
        """这条是不是只发了一张图：是就返回 (认图用的键, 图片段)"""
        comps = event.get_messages()
        images = [c for c in comps if isinstance(c, Image)]
        others = [c for c in comps if not isinstance(c, Image) and not (isinstance(c, Plain) and not c.text.strip())]
        if len(images) != 1 or others:
            return "", None
        image = images[0]
        file = str(image.file or "")
        found = re.search(r"[0-9a-fA-F]{32}", os.path.basename(file.split("?")[0])) if not file.startswith("base64://") else None
        if found:
            return found.group(0).lower(), image
        url = str(image.url or "")
        if url.startswith(("http://", "https://")):
            return url.split("?")[0], image
        if file.startswith("base64://"):
            return "b64:" + hashlib.sha1(file.encode()).hexdigest(), image
        return "", None

    def _allowed(self, group: str, now: float) -> bool:
        if self.cooldown and now - self.last_sent.get(group, 0) < self.cooldown:
            return False
        day = datetime.datetime.now(TZ).date().isoformat()
        seen_day, count = self.today.get(group, (day, 0))
        return not (self.daily_limit and seen_day == day and count >= self.daily_limit)

    def _count(self, group: str, now: float) -> int:
        day = datetime.datetime.now(TZ).date().isoformat()
        seen_day, count = self.today.get(group, (day, 0))
        count = count + 1 if seen_day == day else 1
        self.today[group] = (day, count)
        self.last_sent[group] = now
        return count

    async def fetch(self, image: Image) -> bytes:
        file = str(image.file or "")
        if file.startswith("base64://"):
            return base64.b64decode(file[9:])
        url = str(image.url or "") or (file if file.startswith(("http://", "https://")) else "")
        if not url:
            return b""
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return b""
                data = await resp.content.read(MAX_BYTES + 1)
        return data if len(data) <= MAX_BYTES else b""

    async def observe(self, event: AstrMessageEvent) -> bool:
        """每条群消息都过一遍；该跟就发图，返回发没发（main.py 在只回私聊之后接上，不终止消息）"""
        group = str(event.get_group_id() or "")
        sender = str(event.get_sender_id() or "")
        if not group or not sender or sender == str(event.get_self_id()):
            return False
        key, image = self.image_of(event)
        streak = self.recent.setdefault(group, deque(maxlen=self.min_people))
        if not key or (streak and streak[-1][0] != key):
            streak.clear()
            self.decided.pop(group, None)
        if not key:
            return False
        streak.append((key, sender))
        if len(streak) < self.min_people or len({s for _, s in streak}) < self.min_people:
            return False
        if self.decided.get(group) == key:
            return False
        self.decided[group] = key  # 同一串只判一次
        now = time.time()
        if not self._allowed(group, now) or random.randint(1, 100) > self.probability:
            return False
        try:
            data = await self.fetch(image)
        except Exception as e:  # noqa: BLE001 - 取不回来就不跟，不影响后面的插件
            logger.warning(f"[image_repeat] {event.unified_msg_origin} 图片取不回来，这次不跟：{type(e).__name__}")
            return False
        if not data:
            return False
        await event.send(MessageChain([Image.fromBase64(base64.b64encode(data).decode())]))
        n = self._count(group, now)
        logger.info(f"[image_repeat] {event.unified_msg_origin} 有 {self.min_people} 个人连着发同一张图，她跟了一张（今天第 {n} 次）")
        return True
