"""图片复读：群里连着几个人发同一张图（多半是表情包），她也跟一张，像群友那样凑个热闹。

陪伴插件的复读机只认文字，纯图片消息一律当「[图片]」占位跳过；这里补上图片这一半，不调模型。
- 「同一张」：AstrBot 收到图片会先下载成本地临时文件，再把图片段的 file、url、path 都换成
  「media_image_随机串.jpg」，原来的文件名没了。所以先看原始 OneBot 消息里的图片段：微信连接器给表情包的
  文件名就是原图 md5（QQ 的多半也是），有就认它；没有就认原始的完整下载地址（微信表情包的地址去掉参数后
  都一样，不能去参数）；再没有就读本地临时文件、按内容算摘要。
- 要连着 min_count 条都是这张图，同一个人连发也算（distinct_people 打开时才要求这么多个不同的人）；
  中间插进别的话就重新数。
- 同一串只判一次，按 probability 掷骰；每个群有冷却和每天上限。凑够人数时不管跟没跟都记一行判定，方便查。
- 发的是原图：优先读 AstrBot 下载好的本地临时文件，没有再按地址下载，按 base64 发。
  微信上要发成表情（按表情大小显示、动图会动）：微信连接器 0.14.0 起，1MB 以内的 GIF 原样粘贴就是表情；
  静态的 PNG/JPG 粘贴是普通图片、显示大一截，所以先转成单帧 GIF 再发。
"""
import base64
import datetime
import hashlib
import os
import random
import re
import time
from collections import deque
from collections.abc import Mapping

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.message.components import Image, Plain

MAX_BYTES = 5 * 1024 * 1024


def as_gif(data: bytes) -> bytes:
    """静态图转成单帧 GIF（微信粘贴 GIF 才当表情发）；转不了返回空"""
    import io

    from PIL import Image as PILImage
    try:
        with PILImage.open(io.BytesIO(data)) as im:
            im = im.convert("RGBA")
            im.thumbnail((360, 360))
            alpha = im.getchannel("A")
            frame = im.convert("RGB").convert("P", palette=PILImage.Palette.ADAPTIVE, colors=255)
            mask = alpha.point(lambda a: 255 if a < 128 else 0)
            frame.paste(255, mask)  # 透明的地方用第 255 号色，存成透明
            out = io.BytesIO()
            frame.save(out, "GIF", transparency=255)
            return out.getvalue()
    except Exception:  # noqa: BLE001 - 转不了就按原图发
        return b""
TZ = datetime.timezone(datetime.timedelta(hours=8))


class ImageRepeat:
    def __init__(self, cfg: dict):
        # 工具箱「image_repeat」一节
        self.min_count = max(2, int(cfg.get("min_count", 3)))
        self.distinct_people = bool(cfg.get("distinct_people", False))
        self.probability = min(100, max(0, int(cfg.get("probability", 100))))
        self.cooldown = max(0, int(cfg.get("cooldown_minutes", 10))) * 60
        self.daily_limit = max(0, int(cfg.get("daily_limit", 5)))
        self.recent: dict[str, deque] = {}  # 群 → 最近连着的 (图片, 发的人)
        self.decided: dict[str, str] = {}  # 群 → 这一串已经判过的图片
        self.last_sent: dict[str, float] = {}
        self.today: dict[str, tuple[str, int]] = {}  # 群 → (日期, 今天跟了几次)
        who = "、来自不同的人" if self.distinct_people else "（同一个人连发也算）"
        logger.info(f"[image_repeat] 群里连着 {self.min_count} 条同一张图{who}时，{self.probability}% 跟一张")

    @staticmethod
    def _raw_image_data(event: AstrMessageEvent) -> dict:
        """原始 OneBot 消息里唯一那个图片段的 data（AstrBot 的 Image 已经被换成本地临时文件）"""
        raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
        segments = raw.get("message") if isinstance(raw, Mapping) else None
        images = [s.get("data") for s in segments or [] if isinstance(s, Mapping) and s.get("type") == "image"]
        return dict(images[0]) if len(images) == 1 and isinstance(images[0], Mapping) else {}

    @staticmethod
    def _local_path(image: Image) -> str:
        for value in (getattr(image, "path", ""), image.file, image.url):
            value = str(value or "")
            value = value[7:] if value.startswith("file://") else value
            if value.startswith("/") and os.path.isfile(value):
                return value
        return ""

    @classmethod
    def image_of(cls, event: AstrMessageEvent) -> tuple[str, Image | None]:
        """这条是不是只发了一张图：是就返回 (认图用的键, 图片段)"""
        comps = event.get_messages()
        images = [c for c in comps if isinstance(c, Image)]
        others = [c for c in comps if not isinstance(c, Image) and not (isinstance(c, Plain) and not c.text.strip())]
        if len(images) != 1 or others:
            return "", None
        image = images[0]
        raw = cls._raw_image_data(event)
        for name in (raw.get("file"), image.file):
            name = str(name or "")
            if name and not name.startswith("base64://"):
                found = re.fullmatch(r"([0-9a-fA-F]{32})(\.\w+)?", os.path.basename(name.split("?")[0]))
                if found:
                    return found.group(1).lower(), image
        for url in (raw.get("url"), image.url):
            url = str(url or "")
            if url.startswith(("http://", "https://")):
                return url, image
        file = str(image.file or "")
        if file.startswith("base64://"):
            return "b64:" + hashlib.sha1(file.encode()).hexdigest(), image
        local = cls._local_path(image)
        if local and os.path.getsize(local) <= MAX_BYTES:
            with open(local, "rb") as f:
                return "sha1:" + hashlib.sha1(f.read()).hexdigest(), image
        return "", None

    def _blocked(self, group: str, now: float) -> str:
        """冷却或到了每天上限就返回原因，能跟返回空串"""
        if self.cooldown and now - self.last_sent.get(group, 0) < self.cooldown:
            return "冷却中"
        day = datetime.datetime.now(TZ).date().isoformat()
        seen_day, count = self.today.get(group, (day, 0))
        return "今天已经跟满了" if self.daily_limit and seen_day == day and count >= self.daily_limit else ""

    def _count(self, group: str, now: float) -> int:
        day = datetime.datetime.now(TZ).date().isoformat()
        seen_day, count = self.today.get(group, (day, 0))
        count = count + 1 if seen_day == day else 1
        self.today[group] = (day, count)
        self.last_sent[group] = now
        return count

    async def fetch(self, image: Image, raw_url: str = "") -> bytes:
        file = str(image.file or "")
        if file.startswith("base64://"):
            return base64.b64decode(file[9:])
        local = self._local_path(image)
        if local:
            with open(local, "rb") as f:
                data = f.read(MAX_BYTES + 1)
            if data and len(data) <= MAX_BYTES:
                return data
        candidates = (raw_url, str(image.url or ""), file)
        url = next((u for u in candidates if u.startswith(("http://", "https://"))), "")
        if not url:
            return b""
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[image_repeat] 原图下载失败：状态码 {resp.status}")
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
        streak = self.recent.setdefault(group, deque(maxlen=self.min_count))
        if not key or (streak and streak[-1][0] != key):
            streak.clear()
            self.decided.pop(group, None)
        if not key:
            return False
        streak.append((key, sender))
        if len(streak) < self.min_count:
            return False
        if self.distinct_people and len({s for _, s in streak}) < self.min_count:
            return False
        if self.decided.get(group) == key:
            return False
        self.decided[group] = key  # 同一串只判一次
        now = time.time()
        head = f"[image_repeat] {event.unified_msg_origin} 连着 {self.min_count} 条同一张图"
        blocked = self._blocked(group, now)
        if blocked:
            logger.info(f"{head}，{blocked}，不跟")
            return False
        if random.randint(1, 100) > self.probability:
            logger.info(f"{head}，这次没掷中（{self.probability}%），不跟")
            return False
        try:
            data = await self.fetch(image, str(self._raw_image_data(event).get("url") or ""))
        except Exception as e:  # noqa: BLE001 - 取不回来就不跟，不影响后面的插件
            logger.warning(f"[image_repeat] {event.unified_msg_origin} 图片取不回来，这次不跟：{type(e).__name__}")
            return False
        if not data:
            logger.info(f"{head}，原图取不回来，不跟")
            return False
        if str(event.unified_msg_origin).startswith("wechat") and not data.startswith((b"GIF87a", b"GIF89a")):
            data = as_gif(data) or data
        await event.send(MessageChain([Image.fromBase64(base64.b64encode(data).decode())]))
        n = self._count(group, now)
        logger.info(f"{head}，她跟了一张（今天第 {n} 次）")
        return True
