"""大肥鱼工具箱的测试：配置清单、开关、各模块搬过来以后的基本行为。

要在装了 AstrBot 的环境里跑，插件目录的上一级要在 sys.path 里（按包导入，相对导入才对）：
    ASTRBOT_ROOT=/tmp/dafeiyu-test PYTHONPATH=/AstrBot:<plugin 的上一级> python -m pytest <插件目录>/tests
"""
import asyncio
import json
import os
import re
import sys
from types import SimpleNamespace

import pytest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.basename(PLUGIN_DIR)
sys.path.insert(0, os.path.dirname(PLUGIN_DIR))

SUPPORTED_TYPES = {"int", "float", "bool", "string", "text", "list", "file", "object", "template_list", "dict"}


def schema() -> dict:
    with open(os.path.join(PLUGIN_DIR, "_conf_schema.json"), encoding="utf-8") as f:
        return json.load(f)


def defaults(section: str) -> dict:
    return {k: v.get("default") for k, v in schema()[section]["items"].items() if k != "enabled"}


def mod(name: str):
    __import__(f"{PKG}.modules.{name}")
    return sys.modules[f"{PKG}.modules.{name}"]


class FakeContext:
    def __init__(self, config=None):
        self.config = config or {"provider": [], "admins_id": []}
        self.unregistered = []
        self.conversation_manager = None

    def get_config(self, umo=None):
        return self.config

    def unregister_llm_tool(self, name):
        self.unregistered.append(name)


class FakeEvent:
    def __init__(self, platform="default", group_id="", wake=False):
        self.platform = platform
        self.group_id = group_id
        self.is_at_or_wake_command = wake
        self.unified_msg_origin = f"{platform}:GroupMessage:{group_id}"
        self.stopped = False

    def get_platform_id(self):
        return self.platform

    def get_group_id(self):
        return self.group_id

    def stop_event(self):
        self.stopped = True


# ---------------- 配置清单 ----------------

def test_schema_types_are_supported():
    for section, node in schema().items():
        assert node["type"] == "object", section
        for key, leaf in node["items"].items():
            assert leaf["type"] in SUPPORTED_TYPES, f"{section}.{key}"
            assert "enabled" in node["items"], section


def test_code_only_reads_keys_listed_in_schema():
    """代码里按名字读的配置项都要在清单里，不然 AstrBot 启动时会把它删掉、功能悄悄失效"""
    listed = {k for node in schema().values() for k in node["items"]}
    pattern = re.compile(r"""(?:cfg|loaded)(?:\.get\(|\[)["']([a-z_]+)["']""")
    files = [os.path.join(PLUGIN_DIR, "main.py")] + [
        os.path.join(PLUGIN_DIR, "modules", n) for n in os.listdir(os.path.join(PLUGIN_DIR, "modules")) if n.endswith(".py")
    ]
    read = set()
    for path in files:
        with open(path, encoding="utf-8") as f:
            read |= set(pattern.findall(f.read()))
    assert read, "一个配置项都没找到，正则写错了"
    read -= {"provider", "admins_id"}  # face 读的是 AstrBot 主配置里的这两项，不归插件配置管
    assert read <= listed, sorted(read - listed)


def test_face_defaults_match_schema():
    assert defaults("face") == mod("face").DEFAULT_CONFIG


def test_pat_and_welcome_defaults_match_schema():
    for name in ("pat", "welcome"):
        code = dict(mod(name).DEFAULTS)
        sch = defaults(name)
        assert sch.pop("prompt") == ""  # 面板里留空 = 用代码里的默认提示
        code.pop("prompt")
        assert sch == code, name
        assert mod(name).load_config({"prompt": ""})["prompt"] == mod(name).DEFAULT_PROMPT


def test_voice_sing_selfie_defaults_match_schema():
    voice = mod("voice").Voice(FakeContext(), {})
    d = defaults("voice")
    assert (voice.provider_id, voice.max_chars, voice.rvc_url, voice.rvc_token, voice.rvc_timeout, voice.loudness) == (
        d["tts_provider_id"], d["max_chars"], d["rvc_url"], d["rvc_token"], d["rvc_timeout_seconds"], d["loudness_lufs"])
    sing = mod("sing").Sing({})
    d = defaults("sing")
    assert (sing.url, sing.token, sing.timeout) == (d["service_url"], d["token"], d["timeout_seconds"])
    selfie = mod("selfie").Selfie({})
    assert defaults("selfie") == {"photo_dir": "", "daily_limit": selfie.daily_limit, "recent_count": selfie.recent_count}


def test_platform_hint_defaults_match_schema():
    ph = mod("platform_hint")
    assert ph.parse_platforms(defaults("platform_hint")["platforms"]) == ph.DEFAULTS["platforms"]
    assert defaults("platform_hint")["default_name"] == ph.DEFAULTS["default_name"]


# ---------------- 各模块 ----------------

def test_private_only_drops_unlisted_groups():
    gate = mod("private_only").PrivateOnly({"allowed_groups": ["111", " 222 "]})
    for gid, stopped in (("111", False), ("222", False), ("333", True)):
        event = FakeEvent(group_id=gid)
        asyncio.run(gate.drop_group_message(event))
        assert event.stopped is stopped, gid


def test_platform_hint_marks_platform_once():
    ph = mod("platform_hint").PlatformHint({"platforms": ["wechat=微信", "写坏的一行"], "default_name": "QQ"})
    req = SimpleNamespace(system_prompt="人格")
    asyncio.run(ph.inject_platform(FakeEvent("wechat"), req))
    asyncio.run(ph.inject_platform(FakeEvent("wechat"), req))
    assert req.system_prompt.count("【当前平台】") == 1
    assert req.system_prompt.endswith("【当前平台】这条消息来自微信。")
    req = SimpleNamespace(system_prompt="")
    asyncio.run(ph.inject_platform(FakeEvent("default"), req))
    assert req.system_prompt == "【当前平台】这条消息来自QQ。"


def test_face_module_loads_dictionaries_and_identities():
    face = mod("face").FaceConvert(FakeContext({"provider": [], "admins_id": ["10001"]}),
                                   {"owner_ids": ["wechat:abc"], "partner_ids": ["20002"], "enabled": True})
    assert len(face.face_map) > 300 and face.wx_names
    assert face._identity("default", "10001") == "主人"      # AstrBot 管理员
    assert face._identity("wechat", "abc") == "主人"
    assert face._identity("default", "abc") == ""            # 带平台的只在那个平台算
    assert face._identity("wechat", "20002") == "女主人"
    assert face.dashscope_key == ""


def test_face_borrows_dashscope_key_in_configured_order():
    providers = [
        {"id": "bailian_rerank", "rerank_api_key": "rerank-key"},
        {"id": "dashscope_embedding", "embedding_api_key": "embedding-key"},
        {"id": "other", "api_key": "other-key"},
    ]
    face_mod = mod("face")
    face = face_mod.FaceConvert(FakeContext({"provider": providers, "admins_id": []}), {})
    assert (face.dashscope_key, face.dashscope_key_from) == ("embedding-key", "dashscope_embedding")
    providers.append({"id": "dashscope_tts", "api_key": "tts-key"})  # 原来的提供商还在就照旧用它
    face = face_mod.FaceConvert(FakeContext({"provider": providers, "admins_id": []}), {})
    assert face.dashscope_key_from == "dashscope_tts"
    face = face_mod.FaceConvert(FakeContext({"provider": providers, "admins_id": []}), {"dashscope_key_providers": ["nope"]})
    assert face.dashscope_key == ""

class GroupEvent:
    """群消息：带真的消息段，看给她的指向说明"""

    def __init__(self, comps, self_id="900", sender="小红"):
        self.comps = comps
        self.self_id = self_id
        self.sender = sender
        self.unified_msg_origin = "wechat:GroupMessage:1"

    def get_self_id(self):
        return self.self_id

    def get_sender_name(self):
        return self.sender

    def get_messages(self):
        return self.comps


def test_reply_direction_has_only_a_switch():
    assert defaults("reply_direction") == {}


def test_reply_direction_tells_her_who_is_being_addressed():
    from astrbot.core.message.components import At, AtAll, Plain, Reply

    gate = mod("reply_direction").ReplyDirection({})
    her = lambda: Reply(id="1", sender_id="900")  # noqa: E731
    hint = gate.hint_for(GroupEvent([her(), At(qq="123", name="小明"), Plain(text="你看她说的")]))
    assert hint.startswith("【这句在跟谁说】小红引用了你之前说的话，但 @ 的是小明，不是你")
    assert "别当成小红在问你" in hint
    both = gate.hint_for(GroupEvent([her(), At(qq="900", name="大肥鱼"), At(qq="123", name="小明"), Plain(text="你俩说")]))
    assert "同时 @ 了你和小明" in both
    many = gate.hint_for(GroupEvent([her()] + [At(qq=str(i), name=f"人{i}") for i in range(4)] + [At(qq="0", name="人0")]))
    assert "@ 的是人0、人1、人2等人" in many  # 重复 @ 同一人只算一次，最多点名三个
    assert "号码 123" in gate.hint_for(GroupEvent([her(), At(qq="123", name=""), Plain(text="看")]))
    for name, comps in (
        ("只引用她、没 @ 人", [her(), Plain(text="真的假的")]),
        ("@ 全体", [her(), AtAll(), Plain(text="都来看")]),
        ("引用的是别人", [Reply(id="2", sender_id="555"), At(qq="123", name="小明"), Plain(text="你看")]),
        ("没引用", [At(qq="123", name="小明"), Plain(text="你看")]),
    ):
        assert gate.hint_for(GroupEvent(comps)) == "", name


def test_reply_direction_hint_goes_into_this_turn_only():
    from astrbot.core.message.components import At, Plain, Reply

    gate = mod("reply_direction").ReplyDirection({})
    req = SimpleNamespace(system_prompt="人格", extra_user_content_parts=[])
    event = GroupEvent([Reply(id="1", sender_id="900"), At(qq="123", name="小明"), Plain(text="你看")])
    assert asyncio.run(gate.add_hint(event, req)) is True
    assert req.system_prompt == "人格"  # 不动系统提示词，缓存不受影响
    (part,) = req.extra_user_content_parts
    assert part.text.startswith("【这句在跟谁说】") and part.model_dump_for_context().get("_no_save") is True
    req = SimpleNamespace(system_prompt="人格", extra_user_content_parts=[])
    assert asyncio.run(gate.add_hint(GroupEvent([Plain(text="普通的话")]), req)) is False
    assert req.extra_user_content_parts == []


def test_selfie_daily_limit_and_recent_survive_restart(tmp_path):
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    for i in range(4):
        (photo_dir / f"{i}.jpg").write_bytes(b"x")
    (photo_dir / "photos.json").write_text("{}", encoding="utf-8")
    selfie_mod = mod("selfie")

    class Chat:
        unified_msg_origin = "wechat:GroupMessage:1"
        sent = []

        async def send(self, chain):
            self.sent.append(chain)

    selfie = selfie_mod.Selfie({"photo_dir": str(photo_dir), "daily_limit": 2, "recent_count": 3})
    selfie.state_path = str(tmp_path / "sent.json")
    selfie.state = {}
    chat = Chat()
    for _ in range(2):
        assert "已经发出去了" in asyncio.run(selfie.send_selfie(chat))
    assert asyncio.run(selfie.send_selfie(chat)) == selfie_mod.ENOUGH_TODAY  # 第三张不发
    assert len(chat.sent) == 2
    entry = selfie.state[chat.unified_msg_origin]
    assert entry["count"] == 2 and len(set(entry["recent"])) == 2  # 同一个聊天两张不重复

    again = selfie_mod.Selfie({"photo_dir": str(photo_dir), "daily_limit": 2, "recent_count": 3})
    again.state_path = selfie.state_path
    again.state = again._load_state()  # 重启后记录还在：今天照样不发
    assert asyncio.run(again.send_selfie(chat)) == selfie_mod.ENOUGH_TODAY
    again.state[chat.unified_msg_origin]["date"] = "2000-01-01"  # 换了一天就重新算
    assert "已经发出去了" in asyncio.run(again.send_selfie(chat))
    assert len(set(again.state[chat.unified_msg_origin]["recent"])) == 3


class WakeEvent:
    """群里或私聊里叫她的一条消息"""

    def __init__(self, comps, group_id="1", wake=True):
        self.comps, self.group_id, self.is_at_or_wake_command = comps, group_id, wake

    def get_group_id(self):
        return self.group_id

    def get_messages(self):
        return self.comps


def test_brevity_and_habit_defaults_match_schema(tmp_path):
    assert mod("group_brevity").GroupBrevity({}).short_chars == defaults("group_brevity")["short_chars"]
    hc = mod("habit_check").HabitCheck({}, str(tmp_path / "db"), str(tmp_path / "notes.json"))
    d = defaults("habit_check")
    assert (hc.run_at, hc.recent_per_chat) == (d["run_at"], d["recent_per_chat"])


def test_group_brevity_hints_only_short_group_wakes():
    from astrbot.core.message.components import At, Plain

    gate = mod("group_brevity").GroupBrevity({"short_chars": 15})
    hint = gate.hint_for(WakeEvent([At(qq="900", name="大肥鱼"), Plain(text=" 哈哈哈 [doge]")]))
    assert hint.startswith("【回短点】对方这句就 3 个字")
    assert gate.hint_for(WakeEvent([Plain(text="这句话说得比较长一点，超过十五个字了吧应该是")])) == ""
    assert gate.hint_for(WakeEvent([Plain(text="在吗")], group_id="")) == ""  # 私聊不管
    assert gate.hint_for(WakeEvent([Plain(text="在吗")], wake=False)) == ""  # 没叫她
    assert gate.hint_for(WakeEvent([At(qq="900", name="大肥鱼")])) == ""  # 只 @、只发图不管
    proactive = WakeEvent([Plain(text="在吗")])
    proactive.private_companion_proactive_framework = True
    assert gate.hint_for(proactive) == ""
    req = SimpleNamespace(system_prompt="人格", extra_user_content_parts=[])
    assert asyncio.run(gate.add_hint(WakeEvent([Plain(text="6")]), req)) is True
    assert req.system_prompt == "人格" and req.extra_user_content_parts[0].model_dump_for_context().get("_no_save")


def _turn(user, reply, tool=False):
    msgs = [{"role": "user", "content": [{"type": "text", "text": f"[群友 甲(123)] {user}"},
                                         {"type": "text", "text": "<system_reminder>很长的上下文</system_reminder>"}]}]
    if tool:
        msgs += [{"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]}, {"role": "tool", "content": "结果"}]
    return msgs + [{"role": "assistant", "content": reply}]


def test_habit_check_counts_habits_and_writes_notes(tmp_path):
    import sqlite3

    hc_mod = mod("habit_check")
    group = []
    for i in range(20):
        group += _turn("哈哈", f"行，这个我懂{i}\n不过说来话长（尾巴甩了一下）")
    group += _turn("查下价格", "行情：参照价差多少多少，捡漏提醒" * 3, tool=True)  # 调了工具的不算
    group.append({"role": "assistant", "content": "[CronJob] 每小时查一次"})
    private = _turn("早", "早呀")
    replies = hc_mod.replies_of(group, True, 40)
    assert len(replies) == 21 and replies[0]["other_len"] == 2 and replies[-1]["tooled"]
    stats = hc_mod.analyze(replies + hc_mod.replies_of(private, False, 40))
    assert stats["group_short"] == 20 and stats["group_short_multi"] == 100 and stats["group_actions"] == 20
    assert stats["openers"][0] == ("行", 20)
    notes = hc_mod.make_notes(stats)
    assert len(notes["group"] + notes["all"]) <= 3
    assert any("拆成好几条" in x for x in notes["group"]) and any("括号动作" in x for x in notes["group"])
    assert any("「行」" in x for x in notes["all"])

    db = tmp_path / "data_v4.db"
    con = sqlite3.connect(db)
    con.execute("create table conversations (user_id text, content text)")
    con.execute("insert into conversations values (?, ?)", ("wechat:GroupMessage:1", json.dumps(group, ensure_ascii=False)))
    con.execute("insert into conversations values (?, ?)", ("wechat:FriendMessage:2", json.dumps(private, ensure_ascii=False)))
    con.commit()
    con.close()
    hc = hc_mod.HabitCheck({}, str(db), str(tmp_path / "out" / "notes.json"))
    hc.refresh()
    assert json.load(open(tmp_path / "out" / "notes.json", encoding="utf-8"))["group"]
    group_hint = hc.hint_for(WakeEvent([]))
    private_hint = hc.hint_for(WakeEvent([], group_id=""))
    assert group_hint.startswith("【最近说话的小毛病】") and "拆成好几条" in group_hint
    assert "拆成好几条" not in private_hint and "「行」" in private_hint  # 群里的毛病只在群里提醒
    assert hc.hint_for(WakeEvent([], wake=False)) == ""
    hc.start()  # 测试里没有在跑的事件循环：不挂任务、不报错
    assert hc.task is None


class ImageEvent:
    """群里一条消息：发的人、消息段；send 记下她发出去的"""

    sent = []

    def __init__(self, sender, comps, group_id="1", self_id="900"):
        self.sender, self.comps, self.group_id, self.self_id = sender, comps, group_id, self_id
        self.unified_msg_origin = f"wechat:GroupMessage:{group_id}"

    def get_group_id(self):
        return self.group_id

    def get_sender_id(self):
        return self.sender

    def get_self_id(self):
        return self.self_id

    def get_messages(self):
        return self.comps

    async def send(self, chain):
        ImageEvent.sent.append(chain)


def test_image_repeat_defaults_match_schema():
    ir = mod("image_repeat").ImageRepeat({})
    d = defaults("image_repeat")
    assert (ir.min_count, ir.distinct_people, ir.probability, ir.cooldown // 60, ir.daily_limit) == (
        d["min_count"], d["distinct_people"], d["probability"], d["cooldown_minutes"], d["daily_limit"])


def test_image_repeat_follows_three_in_a_row():
    from astrbot.core.message.components import Image, Plain

    ir_mod = mod("image_repeat")

    async def fake_fetch(image, raw_url=""):
        return b"GIF89a-fake"

    md5 = "0123456789abcdef0123456789ABCDEF"
    sticker = lambda: Image(file=f"{md5}.gif", url="http://cdn.example/x?token=1")  # noqa: E731
    other = lambda: Image(file="b" * 32 + ".png")  # noqa: E731

    ir = ir_mod.ImageRepeat({"min_count": 3, "probability": 100, "cooldown_minutes": 0, "daily_limit": 2})
    ir.fetch = fake_fetch
    ImageEvent.sent = []

    def run(sender, comps, group="1", gate=ir):
        return asyncio.run(gate.observe(ImageEvent(sender, comps, group)))

    assert ir.image_of(ImageEvent("a", [sticker()]))[0] == md5.lower()  # 文件名里的 md5 优先
    assert ir.image_of(ImageEvent("a", [sticker(), Plain(text="哈哈")]))[0] == ""  # 带了字的不算
    # 没有 md5 就认完整地址：微信表情包的地址去掉参数后都一样，不能去参数
    assert ir.image_of(ImageEvent("a", [Image(file="x.jpg", url="https://q.example/a?id=9")]))[0] == "https://q.example/a?id=9"
    assert ir.image_of(ImageEvent("a", [Image(file="x.jpg", url="https://q.example/a?id=8")]))[0] != "https://q.example/a?id=9"
    assert [run("a", [sticker()]), run("a", [sticker()]), run("a", [sticker()])] == [False, False, True]  # 同一个人连发三条也算
    assert len(ImageEvent.sent) == 1
    assert run("b", [sticker()]) is False  # 同一串只跟一次
    run("c", [Plain(text="哈哈哈")])  # 插进别的话，重新数
    assert [run(x, [other()]) for x in "abc"] == [False, False, True]
    assert [run(x, [sticker()]) for x in "xyz"] == [False, False, False]  # 今天已经跟了 2 次，到上限
    assert [run(x, [sticker()], group="2") for x in "abc"][-1] is True  # 别的群照常
    assert run("900", [sticker()], group="3") is False  # 她自己发的不算

    strict = ir_mod.ImageRepeat({"min_count": 3, "distinct_people": True, "probability": 100, "cooldown_minutes": 0})
    strict.fetch = fake_fetch
    assert [run(x, [sticker()], group="4", gate=strict) for x in "aab"] == [False, False, False]  # 要不同的人：a 连发两次不够
    assert run("c", [sticker()], group="4", gate=strict) is True


def test_image_repeat_reads_raw_md5_and_local_files(tmp_path):
    """AstrBot 会把图片段的 file、url、path 都换成本地临时文件「media_image_随机串.jpg」：
    先认原始消息里的 md5 文件名，没有就按本地文件内容算"""
    from astrbot.core.message.components import Image

    ir = mod("image_repeat").ImageRepeat({"min_count": 3, "probability": 100, "cooldown_minutes": 0})
    md5 = "fedcba9876543210fedcba9876543210"

    def local(name, data):
        path = tmp_path / name
        path.write_bytes(data)
        return Image(file=str(path), url=str(path), path=str(path))

    def wechat_sticker(n):
        event = ImageEvent("a", [local(f"media_image_{n:017x}_abcd.jpg", b"JPEG-" + bytes([n]))])
        event.message_obj = SimpleNamespace(raw_message={"message": [
            {"type": "image", "data": {"file": f"{md5}.gif", "url": f"http://cdn.example/stodownload?filekey={n}"}}]})
        return event

    keys = {ir.image_of(wechat_sticker(n))[0] for n in range(3)}
    assert keys == {md5}  # 本地临时文件名每次不一样、内容也可能不一样，认的是原始 md5
    a = ir.image_of(ImageEvent("a", [local("media_image_00000000000000001_aaaa.jpg", b"same")]))[0]
    b = ir.image_of(ImageEvent("a", [local("media_image_00000000000000002_bbbb.jpg", b"same")]))[0]
    c = ir.image_of(ImageEvent("a", [local("media_image_00000000000000003_cccc.jpg", b"other")]))[0]
    assert a == b != c and a.startswith("sha1:")  # 没有原始数据时按内容认，随机文件名不会被当成 md5

    ImageEvent.sent = []
    assert [asyncio.run(ir.observe(wechat_sticker(n))) for n in range(3)] == [False, False, True]
    assert len(ImageEvent.sent) == 1  # 发的是本地临时文件里的原图，不用再下载


def test_image_repeat_sends_static_as_gif_on_wechat():
    import io

    from PIL import Image as PILImage

    ir_mod = mod("image_repeat")
    png = io.BytesIO()
    PILImage.new("RGBA", (500, 400), (255, 0, 0, 128)).save(png, "PNG")
    gif = ir_mod.as_gif(png.getvalue())
    assert gif.startswith(b"GIF") and max(PILImage.open(io.BytesIO(gif)).size) <= 360
    assert ir_mod.as_gif(b"not an image") == b""


def test_face_normalizes_punctuation_like_before():
    face_mod = mod("face")
    assert face_mod.FaceConvert._normalize_punctuation("好、但是「不行」") == "好，但是“不行”"


# ---------------- 主入口 ----------------

def build(config):
    main = sys.modules.get(f"{PKG}.main") or __import__(f"{PKG}.main", fromlist=["DafeiyuToolkit"])
    ctx = FakeContext()
    return main.DafeiyuToolkit(ctx, config), ctx


def test_toolkit_defaults_build_our_modules_and_skip_astrna():
    kit, ctx = build({})
    for name in ("private_only", "reply_direction", "group_brevity", "habit_check", "image_repeat", "platform_hint", "face",
                 "pat", "welcome", "selfie", "sing", "voice"):
        assert getattr(kit, name) is not None, name
    assert kit.preamble is None and kit.tool_history is None and kit.output_limit is None
    assert ctx.unregistered == []
    assert not any(m.startswith(f"{PKG}.astrna") for m in sys.modules), "开关关着时不该导入 AstrNa 的代码"


def test_toolkit_switches_off_modules_and_their_tools():
    kit, ctx = build({"selfie": {"enabled": False}, "voice": {"enabled": False, "session_tts_commands": False}})
    assert kit.selfie is None and kit.voice is None and kit.sing is not None
    assert sorted(ctx.unregistered) == ["send_selfie", "tts_speak"]
    assert kit.voice_commands is False
    assert asyncio.run(kit.send_selfie(None)) == sys.modules[f"{PKG}.main"].OFF_TOOL_TEXT


def test_one_broken_module_does_not_take_down_others(monkeypatch):
    main = sys.modules.get(f"{PKG}.main") or __import__(f"{PKG}.main", fromlist=["DafeiyuToolkit"])

    def boom(*args, **kwargs):
        raise OSError("字典文件没了")

    monkeypatch.setattr(main, "FaceConvert", boom)
    kit, _ = build({})
    assert kit.face is None
    assert kit.pat is not None and kit.private_only is not None



def test_astrna_modules_install_on_real_astrbot_and_uninstall():
    """三个 AstrNa 功能打开时能装到真 AstrBot 上、插件停用时能卸干净（放在最后：会导入 AstrNa 的代码）"""
    kit, _ = build({
        "hide_tool_preamble": {"enabled": True, "all_groups": True, "all_private": True, "umos": []},
        "tool_history": {"enabled": True},
        "output_limit": {"enabled": True, "max_chars": 300, "provider_id": "", "persona_id": "", "whitelist_umos": []},
    })
    modules = (kit.preamble, kit.tool_history, kit.output_limit)
    assert all(m is not None for m in modules)
    assert all(getattr(m, "_installed", True) for m in modules)
    asyncio.run(kit.terminate())
    assert not any(getattr(m, "_installed", False) for m in modules)

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
