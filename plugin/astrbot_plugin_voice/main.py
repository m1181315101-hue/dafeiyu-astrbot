import asyncio
import json
import os
import re

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Plain, Record
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# [旺柴] 这类表情标记、emoji、markdown 符号不念
TAG_RE = re.compile(r"\[[^\[\]]{1,12}\]")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
MD_RE = re.compile(r"[*_`#>~]")


@register(
    "astrbot_plugin_voice",
    "dafeiyu-local",
    "给她一个 tts_speak 工具：有人要她发语音时，用 TTS 念出来、发成 QQ 语音条",
    "1.0.0",
)
class VoicePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 同目录 config.json，改完需重启 AstrBot
        self.provider_id = "edge_tts"
        self.max_chars = 150
        # 翻唱服务的 /convert：把 TTS 念出来的声音换成她的 RVC 声音；没开或失败就发 TTS 原声
        self.rvc_url = ""
        self.rvc_token = ""
        self.rvc_timeout = 30
        # 发出去之前统一拉到这个响度（LUFS），晓伊原声本来只有 -22 左右，偏小
        self.loudness = -11
        try:
            with open(os.path.join(PLUGIN_DIR, "config.json"), encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.provider_id = str(loaded.get("tts_provider_id", self.provider_id))
                self.max_chars = int(loaded.get("max_chars", self.max_chars))
                self.rvc_url = str(loaded.get("rvc_url", "")).rstrip("/")
                self.rvc_token = str(loaded.get("rvc_token", ""))
                self.rvc_timeout = int(loaded.get("rvc_timeout_seconds", self.rvc_timeout))
                self.loudness = float(loaded.get("loudness_lufs", self.loudness))
        except (OSError, ValueError):
            pass
        logger.info(
            f"[voice] TTS 提供商 {self.provider_id}，每条最多 {self.max_chars} 字，"
            f"变声 {self.rvc_url or '不用'}"
        )

    @staticmethod
    def _restore_edge_tts_headers() -> None:
        """AstrBot 4.29 的 edge_tts 提供商把 edge-tts 的 User-Agent 换成了自己的，微软会回 403；换回 edge-tts 自带的"""
        try:
            from edge_tts.constants import BASE_HEADERS, WSS_HEADERS
        except ImportError:
            return
        WSS_HEADERS["User-Agent"] = BASE_HEADERS["User-Agent"]

    @staticmethod
    def _clean(text: str) -> str:
        text = TAG_RE.sub("", text)
        text = EMOJI_RE.sub("", text)
        text = MD_RE.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    def _truncate(self, text: str) -> str:
        """超长时在最后一个句末标点处截断，不把一句话念一半"""
        if len(text) <= self.max_chars:
            return text
        head = text[: self.max_chars]
        cut = max(head.rfind(p) for p in "。！？!?…~")
        return head[: cut + 1] if cut >= self.max_chars // 2 else head

    async def _to_rvc_voice(self, path: str) -> tuple[str | None, str]:
        """把 TTS 音频送去变声，成功返回 (新文件路径, "")，失败返回 (None, 原因)"""
        if not self.rvc_url:
            return None, "没配变声服务"
        try:
            with open(path, "rb") as f:
                data = f.read()
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.rvc_url}/convert", data=data,
                                  headers={"X-Token": self.rvc_token, "Content-Type": "application/octet-stream"},
                                  timeout=aiohttp.ClientTimeout(total=self.rvc_timeout)) as r:
                    if r.status != 200:
                        return None, f"变声服务 {r.status} {(await r.text())[:80]}"
                    out = await r.read()
        except Exception as e:
            return None, f"变声服务连不上（{type(e).__name__}）"
        new_path = os.path.splitext(path)[0] + "_rvc.wav"
        with open(new_path, "wb") as f:
            f.write(out)
        return new_path, ""

    async def _louder(self, path: str) -> str | None:
        """用 ffmpeg 把响度拉到 self.loudness，峰值压在 -1dB；失败返回 None（照发原文件）"""
        out = os.path.splitext(path)[0] + "_loud.wav"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error", "-i", path,
            "-af", f"loudnorm=I={self.loudness}:TP=-1", "-ac", "1", "-ar", "24000", out,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0 or not os.path.exists(out):
            logger.warning(f"[voice] 调响度失败，照发原声：{err.decode(errors='ignore')[-200:]}")
            return None
        return out

    @filter.llm_tool(name="tts_speak")
    async def tts_speak(self, event: AstrMessageEvent, text: str):
        """用你的声音发一条 QQ 语音条来回答对方。有人让你发语音、用语音回答、说句话给他听、试试声音时调用。
        把你这次要回答的完整内容都放进 text，直接用语音回答，不要只念一句开场白；发完这一轮就不再发文字。

        Args:
            text(string): 这次要用语音说的完整回答，口语、纯文字，不带表情标记，一般不超过四五句
        """
        clean = self._truncate(self._clean(text))
        if not clean:
            return "语音没发出去：要念的内容是空的。用文字跟对方说一句，不要说已经发了语音。"
        provider = self.context.get_provider_by_id(self.provider_id)
        if provider is None or not hasattr(provider, "get_audio"):
            return f"语音没发出去：找不到 TTS 提供商 {self.provider_id}。用文字告诉对方现在发不了语音，不要说已经发了。"
        self._restore_edge_tts_headers()
        path = rvc_path = loud_path = None
        try:
            path = await provider.get_audio(clean)
            rvc_path, why = await self._to_rvc_voice(path)
            loud_path = await self._louder(rvc_path or path)
            await event.send(MessageChain([Record.fromFileSystem(loud_path or rvc_path or path)]))
        except Exception as e:
            logger.error(f"[voice] 语音发送失败：{e}", exc_info=True)
            return "语音没发出去：合成或发送失败。用文字告诉对方语音暂时发不了，不要说已经发了。"
        finally:
            # 发送时已经转成 base64 交给 NapCat，本地文件可以删了
            for p in (path, rvc_path, loud_path):
                if p and os.path.exists(p):
                    os.remove(p)
        voice = "RVC 声音" if rvc_path else f"TTS 原声（{why}）"
        logger.info(f"[voice] 已发语音条 {event.unified_msg_origin}，{len(clean)} 字，{voice}")
        event.set_extra("dafeiyu_voice_sent", True)
        return "Message sent：语音条已经发给对方了，这一轮的文字回复不会再发出去。"

    # 比群聊续聊（10）和表情插件（0）先执行：用语音回答过的这一轮，文字回复整条不发
    @filter.on_decorating_result(priority=20)
    async def voice_only(self, event: AstrMessageEvent):
        if not event.get_extra("dafeiyu_voice_sent"):
            return
        result = event.get_result()
        if result is None or not result.is_llm_result():
            return
        result.chain = [c for c in result.chain if not isinstance(c, Plain)]
