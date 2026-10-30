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
    assert defaults("selfie") == {"photo_dir": ""}


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
    for name in ("private_only", "platform_hint", "face", "pat", "welcome", "selfie", "sing", "voice"):
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
