import asyncio
import json
import os
import random
import time

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Plain, Record
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# 后台唱失败时直接发的话（这时候 LLM 那一轮已经结束了）
FAIL_TEXT = {
    "not_found": ["这首我没找到能唱的版本", "没搜到这首，换一首吧"],
    "busy": ["我还在唱上一首呢，等会儿"],
    "error": ["嗓子卡住了，这首没唱出来", "唱到一半出岔子了，等会儿再试试"],
}


@register(
    "astrbot_plugin_sing",
    "dafeiyu-local",
    "给她一个 sing_song 工具：有人点歌时，调 Mac 上的翻唱服务，用她的声音唱一段副歌发成语音条",
    "1.0.0",
)
class SingPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 同目录 config.json，改完需重启 AstrBot；token 要和 cover/config.json 一致
        self.url = "http://host.docker.internal:8790"
        self.token = ""
        self.timeout = 400
        try:
            with open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.url = str(loaded.get("service_url", self.url)).rstrip("/")
                self.token = str(loaded.get("token", ""))
                self.timeout = int(loaded.get("timeout_seconds", self.timeout))
        except (OSError, ValueError):
            pass
        self.busy = False
        # 后台任务要留引用，不然可能被回收
        self._tasks: set[asyncio.Task] = set()
        logger.info(f"[sing] 翻唱服务 {self.url}")

    async def _health(self) -> dict | None:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.url}/health", headers={"X-Token": self.token},
                                 timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return await r.json() if r.status == 200 else None
        except Exception:
            return None

    async def _sing(self, event: AstrMessageEvent, song: str, passthrough: bool = False) -> None:
        """后台跑：等翻唱服务出结果，发语音条；失败就发一句短话"""
        self.busy = True
        path = None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.url}/cover", json={"query": song, "passthrough": passthrough},
                                  headers={"X-Token": self.token},
                                  timeout=aiohttp.ClientTimeout(total=self.timeout)) as r:
                    if r.status != 200:
                        detail = (await r.text())[:200]
                        kind = "busy" if r.status == 429 else "not_found" if "没搜到" in detail or "读不出来" in detail else "error"
                        logger.warning(f"[sing] 翻唱失败 {r.status}：{detail}")
                        await event.send(MessageChain([Plain(random.choice(FAIL_TEXT[kind]))]))
                        return
                    info = r.headers.get("X-Cover-Info", "")
                    data = await r.read()
            path = os.path.join(get_astrbot_temp_path(), f"sing_{int(time.time() * 1000)}.mp3")
            with open(path, "wb") as f:
                f.write(data)
            await event.send(MessageChain([Record.fromFileSystem(path)]))
            logger.info(f"[sing] 已发翻唱 {event.unified_msg_origin}：{info}")
        except Exception as e:
            logger.error(f"[sing] 翻唱出错：{e}", exc_info=True)
            try:
                await event.send(MessageChain([Plain(random.choice(FAIL_TEXT["error"]))]))
            except Exception:
                pass
        finally:
            self.busy = False
            # 发送时已经转成 base64 交给 NapCat，本地文件可以删了
            if path and os.path.exists(path):
                os.remove(path)

    @filter.llm_tool(name="sing_song")
    async def sing_song(self, event: AstrMessageEvent, song: str):
        """唱歌：有人让你唱一首歌时调用。会自动找到这首歌，用你的声音唱一段副歌，一两分钟后作为语音条发到当前聊天。

        Args:
            song(string): 歌名，知道歌手就带上，比如“晴天 周杰伦”；对方给了歌曲链接就直接填链接
        """
        health = await self._health()
        if health is None:
            return "唱歌服务没开，现在唱不了。用一句话跟对方说现在唱不了，不要假装唱了，也不要把歌词打出来。"
        if not health.get("model"):
            return "你还没有自己的唱歌声音（声音模型还没装好），现在唱不了。用你的口吻跟对方说还没学会唱歌，不要假装唱，也不要把歌词打出来。"
        if self.busy or health.get("busy"):
            return "你正在唱另一首，告诉对方等这首唱完再点。"
        task = asyncio.create_task(self._sing(event, song))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return "已经开始准备了，一两分钟后语音会自动发出来。现在只用一句很短的话让对方等一下，不要说已经唱完，也不要把歌词打出来。"
