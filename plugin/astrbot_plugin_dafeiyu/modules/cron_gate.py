"""盯盘预检：盯盘的定时任务开跑前，先不经过模型把它要查的工具调一遍，没有新东西就不叫她。

- 群友让她建的盯盘任务每半小时跑一次，每次都要叫她起来调三四回模型。2026-11-01 量到：一天七八十次里九成以上查完是空的，
  有一个任务查了 52 次，51 次一件都没有。
- 做法：在 AstrBot 的定时任务管理器上套一层。`_run_job` 每次跑都现取 `_run_active_agent_job`，这里用同名的实例属性盖住它。
  规则里列出的任务开跑时，先直接调规则写的 MCP 工具，用正则从返回的文字里认出编号，跟见过的比：
  全都见过就直接返回，AstrBot 照样记这次「已完成」；有没见过的，才照原样叫她，她按任务原话自己查、自己发。
- 第一次预检不知道她以前提醒过哪些，照常叫她一次，她跑完再把当前的编号记下当底；见过的编号 keep_days 天没再出现就忘掉。
- 拿不准就照原样叫她：工具没接上、报错，返回里明明有列表却一个编号也认不出（多半是格式变了），或者预检自己出了岔子。
- 她那一次跑完才把新编号记成见过；那次跑失败，下一次还会再叫她。
- 面板里的「立即运行」也走这道预检。插件停用时拆掉这一层，任务回到 AstrBot 原来的跑法。
"""
import asyncio
import json
import os
import re
import time
from datetime import timedelta
from typing import NamedTuple

from astrbot.api import logger

DEFAULT_KEY = r"[A-Z]\d{4,}"
# 像列表项的行：「- 」开头，或者用「 | 」分栏。有这种行却一个编号都认不出，就当格式变了
LIST_LINE = re.compile(r"^\s*- \S|\s\|\s", re.M)
ORIGINAL = "_dafeiyu_cron_gate_original"


class Rule(NamedTuple):
    calls: list  # [{"server": "", "tool": "", "args": {}}]
    key: re.Pattern


def parse_rules(text) -> dict:
    """规则是一段 JSON：{"定时任务 ID": {"calls": [{"server": "MCP 服务名，可不写", "tool": "工具名", "args": {}}], "key": "认编号的正则，可不写"}}"""
    text = str(text or "").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("规则要写成一个 JSON 对象，键是定时任务 ID")
    rules = {}
    for job_id, spec in data.items():
        try:
            calls = [_call_spec(c) for c in spec["calls"]]
            if not calls:
                raise ValueError("calls 是空的")
            rules[str(job_id).strip()] = Rule(calls, re.compile(spec.get("key") or DEFAULT_KEY))
        except Exception as exc:  # noqa: BLE001 - 一条写坏了只跳过这一条
            logger.error(f"[cron_gate] 定时任务 {str(job_id)[:8]} 的规则写得不对，这一条先不管：{exc}")
    return rules


def _call_spec(call) -> dict:
    tool = str(call["tool"]).strip()
    args = call.get("args") or {}
    if not tool or not isinstance(args, dict):
        raise ValueError("每一步都要写 tool，args 要是 JSON 对象")
    return {"server": str(call.get("server") or "").strip(), "tool": tool, "args": args}


class CronGate:
    def __init__(self, context, cfg: dict, state_path: str):
        # 工具箱「cron_gate」一节：{"rules": "JSON", "keep_days": 30, "timeout_seconds": 60}
        self.context = context
        self.rules = parse_rules(cfg.get("rules", ""))
        self.keep_seconds = max(1, int(cfg.get("keep_days", 30))) * 86400
        self.timeout = max(5, int(cfg.get("timeout_seconds", 60)))
        self.state_path = state_path
        self.seen = self._load()  # {定时任务 ID: {编号: 最后见到的时间戳}}
        self._lock = asyncio.Lock()  # 两个盯盘常在同一秒开跑，读改写要排队
        self._manager = None
        self._wrapper = None

    # ---------------- 套上、拆掉 ----------------

    def install(self) -> bool:
        if not self.rules:
            logger.warning("[cron_gate] 盯盘预检开着，但一条规则都没有，先不接")
            return False
        manager = getattr(self.context, "cron_manager", None)
        current = getattr(manager, "_run_active_agent_job", None)
        if not callable(current):
            raise RuntimeError("这版 AstrBot 的定时任务管理器对不上（找不到 _run_active_agent_job），定时任务照原样跑")
        original = getattr(current, ORIGINAL, current)  # 上一个实例没拆干净：接回最早的那个

        async def gated(job, *args, **kwargs):
            rule = self.rules.get(str(getattr(job, "job_id", "")))
            if rule is None:
                return await original(job, *args, **kwargs)
            try:
                wake, mark = await self.precheck(job.job_id, rule)
            except Exception as exc:  # noqa: BLE001 - 预检自己出了岔子也照原样叫她，不能让盯盘停掉
                logger.error(f"[cron_gate] 定时任务 {job.job_id[:8]} 预检出错，照常叫她：{exc}", exc_info=True)
                wake, mark = True, None
            if not wake:
                return None
            result = await original(job, *args, **kwargs)  # 她这次跑失败就不记，下一次还会叫她
            if mark is not None:
                await self._remember(job.job_id, mark)
            return result

        setattr(gated, ORIGINAL, original)
        manager._run_active_agent_job = gated
        self._manager, self._wrapper = manager, gated
        logger.info(f"[cron_gate] 盯盘预检接上了：{len(self.rules)} 个定时任务先查一眼，有新东西才叫她"
                    f"（{'、'.join(job_id[:8] for job_id in self.rules)}）")
        return True

    def terminate(self) -> None:
        manager, wrapper = self._manager, self._wrapper
        self._manager = self._wrapper = None
        if manager is None or vars(manager).get("_run_active_agent_job") is not wrapper:
            return
        original = getattr(wrapper, ORIGINAL)
        if getattr(original, "__self__", None) is manager:
            del manager._run_active_agent_job  # 原来就是类上的方法：拿掉实例属性就回去了
        else:
            manager._run_active_agent_job = original

    # ---------------- 预检 ----------------

    async def precheck(self, job_id: str, rule: Rule) -> tuple[bool, list | None]:
        """返回（叫不叫她，她跑完以后要记成见过的编号）；第二项是 None 就不动记录"""
        tag = job_id[:8]
        try:
            text = "\n".join([await self._call(c) for c in rule.calls])
        except Exception as exc:  # noqa: BLE001 - 查不了就照原样叫她
            logger.warning(f"[cron_gate] 定时任务 {tag} 预检没查成，照常叫她：{exc!s:.200}")
            return True, None
        keys = list(dict.fromkeys(m.group(0) for m in rule.key.finditer(text)))
        if not keys and LIST_LINE.search(text):
            logger.warning(f"[cron_gate] 定时任务 {tag} 预检：返回里有列表却认不出编号，可能是格式变了，照常叫她")
            return True, None
        now = time.time()
        async with self._lock:
            seen = self.seen.get(job_id)
            if seen is None:
                logger.info(f"[cron_gate] 定时任务 {tag} 第一次预检：现在有 {len(keys)} 个编号，照常叫她一次，跑完记下当底")
                return True, keys
            fresh = [k for k in keys if k not in seen]
            seen.update((k, now) for k in keys if k in seen)
            for k in [k for k, t in seen.items() if now - t > self.keep_seconds]:
                del seen[k]
            self._save()
        if not fresh:
            logger.info(f"[cron_gate] 定时任务 {tag} 预检："
                        f"{f'{len(keys)} 个编号都见过' if keys else '这次什么都没查到'}，不叫她")
            return False, None
        logger.info(f"[cron_gate] 定时任务 {tag} 预检：有 {len(fresh)} 个新编号"
                    f"（{'、'.join(fresh[:3])}{' 等' if len(fresh) > 3 else ''}），叫她")
        return True, fresh

    async def _call(self, call: dict) -> str:
        """不经过模型直接调 MCP 工具，只要返回里的文字。每次现找客户端：AstrBot 刚起来时 MCP 可能还没连上"""
        manager = self.context.get_llm_tool_manager()
        if call["server"]:
            clients = manager.mcp_client_dict
            if call["server"] not in clients:
                raise RuntimeError(f"MCP 服务 {call['server']} 没接上")
            client, name = clients[call["server"]], call["tool"]
        else:
            func = manager.get_func(call["tool"])
            client = getattr(func, "mcp_client", None)
            name = getattr(getattr(func, "mcp_tool", None), "name", call["tool"])
            if client is None:
                raise RuntimeError(f"找不到 MCP 工具 {call['tool']}")
        result = await client.call_tool_with_reconnect(
            tool_name=name, arguments=dict(call["args"]), read_timeout_seconds=timedelta(seconds=self.timeout))
        text = "\n".join(getattr(c, "text", "") for c in (result.content or []) if getattr(c, "type", "") == "text")
        if getattr(result, "isError", False):
            raise RuntimeError(f"{call['tool']} 报错：{text}")
        return text

    async def _remember(self, job_id: str, keys: list) -> None:
        """第一次跑完时 keys 可能是空的，也要留下这条记录，下次才不算第一次"""
        async with self._lock:
            self.seen.setdefault(job_id, {}).update(dict.fromkeys(keys, time.time()))
            self._save()

    # ---------------- 见过的编号 ----------------

    def _load(self) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as exc:  # noqa: BLE001 - 读坏了就当都没见过，下次重新记底
            logger.warning(f"[cron_gate] 见过的编号读不出来，当都没见过：{exc}")
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(job_id): {str(k): float(t) for k, t in keys.items()}
                for job_id, keys in data.items() if isinstance(keys, dict)}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.seen, f, ensure_ascii=False)
            os.replace(tmp, self.state_path)
        except OSError as exc:
            logger.warning(f"[cron_gate] 见过的编号存不下：{exc}")
