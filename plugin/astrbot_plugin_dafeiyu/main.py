"""大肥鱼工具箱：我们自己写的 8 个小插件合成一个，再加上「引用她又 @ 别人」的指向说明和从 AstrNa 搬来的 3 个可选功能。

一个功能一个模块（modules/、astrna/），各有开关，都在 AstrBot 面板的插件配置里改；面板里保存会自动重载插件。
这里只做三件事：按开关把模块建起来、把 AstrBot 的钩子接给对应模块、插件停用时把 AstrNa 的运行时补丁拆掉。
- 某个模块建不起来（配置写坏、文件缺了）只记一条错误、关掉它自己，别的功能照常；
- 钩子的优先级照搬原来各插件的写法，只有「草稿清理」从 0 提到 1：原来靠插件加载顺序排在记忆插件前面，
  合并后加载顺序变了，写死一级保证它还是先擦完再给记忆插件看；
- 同优先级的几个钩子按原来的加载顺序排：新人欢迎 → 拍一拍 → 收信翻译；@ 新人 → 表情转换；
- AstrNa 的三个模块只在开关打开时才导入：跟 AstrBot 内部结构绑得紧，关着就一行都不执行，
  导不进来也只是那一个功能建不起来。
"""
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .modules import voice as voice_cmds
from .modules.face import FaceConvert
from .modules.pat import Pat
from .modules.platform_hint import PlatformHint
from .modules.private_only import PrivateOnly
from .modules.reply_direction import ReplyDirection
from .modules.selfie import Selfie
from .modules.sing import Sing
from .modules.voice import Voice
from .modules.welcome import Welcome

# 工具名 → 管它的模块；模块关着或建不起来时把工具撤掉，免得她以为自己有这个本事
TOOLS = {"send_selfie": "selfie", "sing_song": "sing", "tts_speak": "voice"}
OFF_TOOL_TEXT = "这个功能现在关着。用一句话跟对方说现在做不了，不要假装做了。"


@register(
    "astrbot_plugin_dafeiyu",
    "dafeiyu-local",
    "大肥鱼工具箱：只回私聊、引用她又 @ 别人时说明在跟谁说、平台提示、表情转换、拍一拍、新人欢迎、发照片、唱歌、发语音，外加 AstrNa 的三个可选功能",
    "1.2.0",
)
class DafeiyuToolkit(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config if config is not None else {}
        self.private_only = self._build("private_only", PrivateOnly)
        self.reply_direction = self._build("reply_direction", ReplyDirection)
        self.platform_hint = self._build("platform_hint", PlatformHint)
        self.face = self._build("face", lambda c: FaceConvert(context, c))
        self.pat = self._build("pat", lambda c: Pat(context, c))
        self.welcome = self._build("welcome", lambda c: Welcome(context, c))
        self.selfie = self._build("selfie", Selfie)
        self.sing = self._build("sing", Sing)
        self.voice = self._build("voice", lambda c: Voice(context, c))
        self.voice_commands = bool(self._section("voice").get("session_tts_commands", True))
        for tool, owner in TOOLS.items():
            if getattr(self, owner) is None:
                self.context.unregister_llm_tool(tool)
                logger.info(f"[dafeiyu] {owner} 关着，撤掉工具 {tool}")

        self.preamble = self._build("hide_tool_preamble", self._make_preamble, default=False)
        self.tool_history = self._build("tool_history", self._make_tool_history, default=False)
        self.output_limit = self._build("output_limit", self._make_output_limit, default=False)
        on = [name for name in ("private_only", "reply_direction", "platform_hint", "face", "pat", "welcome", "selfie", "sing", "voice",
                                "preamble", "tool_history", "output_limit") if getattr(self, name) is not None]
        logger.info(f"[dafeiyu] 开着的功能：{'、'.join(on) or '无'}")

    def _section(self, name: str) -> dict:
        value = self.config.get(name) if hasattr(self.config, "get") else None
        return dict(value) if isinstance(value, dict) else {}

    def _build(self, name: str, factory, *, default: bool = True):
        """开关开着就建模块；建不起来记一条错误、只关掉这一个"""
        cfg = self._section(name)
        if not cfg.get("enabled", default):
            return None
        try:
            return factory(cfg)
        except Exception as exc:  # noqa: BLE001 - 一个模块坏了不能拖垮别的
            logger.error(f"[dafeiyu] {name} 建不起来，这个功能先关掉：{exc}", exc_info=True)
            return None

    @staticmethod
    def _make_preamble(cfg: dict):
        from .astrna.modules.tool_call_preamble import ToolCallPreambleModule

        module = ToolCallPreambleModule(
            logger=logger,
            all_groups=bool(cfg.get("all_groups", False)),
            all_private=bool(cfg.get("all_private", False)),
            umos=cfg.get("umos", []),
        )
        module.install()
        return module

    @staticmethod
    def _make_tool_history(cfg: dict):
        from .astrna.modules.tool_history_context import ToolHistoryContextModule

        module = ToolHistoryContextModule(logger=logger)
        module.install()
        return module

    def _make_output_limit(self, cfg: dict):
        from .astrna.modules.output_length_limiter import OutputLengthLimiterModule

        module = OutputLengthLimiterModule(
            context=self.context,
            logger=logger,
            whitelist_umos=cfg.get("whitelist_umos", []),
            max_chars=cfg.get("max_chars", 50),
            provider_id=str(cfg.get("provider_id", "")),
            persona_id=str(cfg.get("persona_id", "")),
        )
        module.install()
        return module

    async def terminate(self):
        # 过场白门卫要在第一个 await 前停用，免得卸载后还在扣字（AstrNa 的做法）
        for module in (self.preamble, self.tool_history):
            if module is not None:
                module.terminate()
        if self.output_limit is not None:
            self.output_limit.terminate()
            try:
                await self.output_limit.drain_pending_operations(timeout=0.05)
            except Exception:  # noqa: BLE001
                pass

    # ---------------- 收到消息 ----------------

    # priority 越大越先执行：群消息在最前面就终止
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=100000)
    async def private_only_gate(self, event: AstrMessageEvent):
        if self.private_only is not None:
            await self.private_only.drop_group_message(event)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def welcome_newcomer(self, event: AstrMessageEvent):
        if self.welcome is None:
            return
        async for result in self.welcome.on_group_increase(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def pat_reply(self, event: AstrMessageEvent):
        if self.pat is None:
            return
        async for result in self.pat.on_poke(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def face_inbound(self, event: AstrMessageEvent):
        if self.face is not None:
            await self.face.inbound_face_to_text(event)

    # ---------------- 请求 LLM 前后 ----------------

    @filter.on_llm_request(priority=1000)
    async def astrna_sanitize(self, event: AstrMessageEvent, req):
        if self.tool_history is not None:
            self.tool_history.sanitize_request(req)

    @filter.on_llm_request()
    async def platform_inject(self, event: AstrMessageEvent, req):
        if self.platform_hint is not None:
            await self.platform_hint.inject_platform(event, req)

    @filter.on_llm_request()
    async def reply_direction_hint(self, event: AstrMessageEvent, req):
        if self.reply_direction is not None:
            await self.reply_direction.add_hint(event, req)

    @filter.on_llm_response(priority=1)
    async def face_scrub(self, event: AstrMessageEvent, response):
        if self.face is not None:
            await self.face.scrub_drafts(event, response)

    # ---------------- 发送前 ----------------

    # 比群聊续聊（10）和表情转换（0）先执行：用语音回答过的这一轮，文字回复整条不发
    @filter.on_decorating_result(priority=20)
    async def voice_only(self, event: AstrMessageEvent):
        if self.voice is not None:
            await self.voice.voice_only(event)

    @filter.on_decorating_result()
    async def welcome_at(self, event: AstrMessageEvent):
        if self.welcome is not None:
            await self.welcome.add_at(event)

    @filter.on_decorating_result()
    async def face_convert(self, event: AstrMessageEvent):
        if self.face is not None:
            await self.face.convert_faces(event)

    # ---------------- 工具（说明文字就是她看到的工具说明，别随便改） ----------------

    @filter.llm_tool(name="send_selfie")
    async def send_selfie(self, event: AstrMessageEvent, kind: str = "", with_whom: str = "", scene: str = ""):
        """发照片：有人想看你的自拍、照片、生活照、你和同事的合照，或者问你长什么样、问哪位同事长什么样时调用。会从你的相册里挑最贴的一张，原样发到当前聊天。

        Args:
            kind(string): 想要哪种：自拍、生活照、合照；对方没说就留空
            with_whom(string): 想看和哪位同事的合照就填她的名字：Claude、GPT、Gemini、Grok、GLM、Kimi、千问，想看大家一起的就填“大家”；不是就留空
            scene(string): 正在聊的场景或对方想看的内容，比如 吃饭、下雨、晚安、过年、万圣节；没有就留空
        """
        if self.selfie is None:
            return OFF_TOOL_TEXT
        return await self.selfie.send_selfie(event, kind, with_whom, scene)

    @filter.llm_tool(name="sing_song")
    async def sing_song(self, event: AstrMessageEvent, song: str):
        """唱歌：有人让你唱一首歌时调用。会自动找到这首歌，用你的声音唱一段副歌，一两分钟后作为语音条发到当前聊天。

        Args:
            song(string): 歌名，知道歌手就带上，比如“晴天 周杰伦”；对方给了歌曲链接就直接填链接
        """
        if self.sing is None:
            return OFF_TOOL_TEXT
        return await self.sing.sing_song(event, song)

    @filter.llm_tool(name="tts_speak")
    async def tts_speak(self, event: AstrMessageEvent, text: str):
        """用你的声音发一条 QQ 语音条来回答对方。有人让你发语音、用语音回答、说句话给他听、试试声音时调用。
        把你这次要回答的完整内容都放进 text，直接用语音回答，不要只念一句开场白；发完这一轮就不再发文字。

        Args:
            text(string): 这次要用语音说的完整回答，口语、纯文字，不带表情标记，一般不超过四五句
        """
        if self.voice is None:
            return OFF_TOOL_TEXT
        return await self.voice.tts_speak(event, text)

    # ---------------- 指令 ----------------

    @filter.command("语音开")
    async def voice_on(self, event: AstrMessageEvent):
        """开启本会话的语音条。"""
        if self.voice_commands:
            async for result in voice_cmds.voice_on(event):
                yield result

    @filter.command("语音关")
    async def voice_off(self, event: AstrMessageEvent):
        """关闭本会话的语音条（文字照常聊）。"""
        if self.voice_commands:
            async for result in voice_cmds.voice_off(event):
                yield result

    @filter.command("语音状态")
    async def voice_status(self, event: AstrMessageEvent):
        """查询本会话的语音条开关状态。"""
        if self.voice_commands:
            async for result in voice_cmds.voice_status(event):
                yield result
