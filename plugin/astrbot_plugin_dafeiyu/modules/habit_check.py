"""说话习惯自检：每天数一遍她最近的回复，挑出最突出的一两处小毛病，写成提醒放进之后的提示里，第二天再按新数字重写。

不额外调模型，只数数：群里对方说得短时她回多长、拆几条，开头最常用的词，反复出现的口头禅，群里的括号动作。
只读 AstrBot 的对话记录（data_v4.db 的 conversations，只读打开）；对方的话只取长度，不留内容。
每个对话取最近 recent_per_chat 条她的最终回复（不算调工具那几轮、定时任务记录）。
提醒存在 data/plugin_data/astrbot_plugin_dafeiyu/habit_notes.json；每天 run_at（默认 04:30，北京时间）重算，
插件启动时提醒不是今天的也重算一次。提醒只发给模型、不存进聊天历史（mark_as_temp）。
"""
import asyncio
import collections
import datetime
import json
import os
import re
import sqlite3
import statistics

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.agent.message import TextPart

TZ = datetime.timezone(datetime.timedelta(hours=8))
FACE = re.compile(r"\[[^\[\]]{1,8}\]")
QUOTE = re.compile(r"<Quoted Message>.*?</Quoted Message>", re.S)
HEADER = re.compile(r"^\s*\[[^\]]*\]\s*")  # 用户消息开头的「[昵称 身份(号)]」
ACTION = re.compile(r"[（(]([一-鿿]{2,8})[）)]")
OPENER = re.compile(r"[^，,。！!？?~～…\s]{1,4}")


def _first_text(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    for p in c or []:
        if isinstance(p, dict) and p.get("type") == "text":
            return p.get("text", "")
    return ""


def _all_text(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") for p in c or [] if isinstance(p, dict) and p.get("type") == "text")


def replies_of(history: list, group: bool, limit: int) -> list[dict]:
    """一段对话里她最近的最终回复：{group, other_len, text, tooled}"""
    out, other, tooled = [], None, False
    for m in history if isinstance(history, list) else []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "user":
            said = HEADER.sub("", QUOTE.sub("", _first_text(m)).strip())
            other, tooled = len(re.sub(r"\s+", "", FACE.sub("", said))), False
        elif role == "tool" or (role == "assistant" and m.get("tool_calls")):
            tooled = True
        elif role == "assistant" and other is not None:
            text = _all_text(m).strip()
            if text and not text.startswith("[CronJob]"):
                out.append({"group": group, "other_len": other, "text": text, "tooled": tooled})
            other = None
    return out[-limit:]


def analyze(replies: list[dict]) -> dict:
    chat = [r for r in replies if not r["tooled"]]
    short = [r for r in chat if r["group"] and 0 < r["other_len"] <= 5]
    lens = [len(re.sub(r"\s+", "", FACE.sub("", r["text"]))) for r in short]
    openers = collections.Counter()
    grams = collections.Counter()
    for r in chat:
        clean = re.sub(r"\s+", "", FACE.sub("", r["text"]))
        found = OPENER.match(clean)
        if found:
            openers[found.group(0)] += 1
        seen = set()
        for n in (4, 5, 6):
            for i in range(len(clean) - n + 1):
                g = clean[i:i + n]
                if re.fullmatch(r"[一-鿿]+", g):
                    seen.add(g)
        grams.update(seen)
    phrases = [(g, k) for g, k in grams.most_common(40) if k >= 6]
    phrases = [(g, k) for g, k in phrases if not any(g != h and g in h and m >= k * 0.8 for h, m in phrases)]
    return {
        "replies": len(chat),
        "group_short": len(short),
        "group_short_median": statistics.median(lens) if lens else 0,
        "group_short_multi": (sum("\n" in r["text"].strip() for r in short) * 100 // len(short)) if short else 0,
        "openers": openers.most_common(3),
        "phrases": phrases[:3],
        "group_actions": sum(len(ACTION.findall(r["text"])) for r in chat if r["group"]),
    }


def make_notes(stats: dict) -> dict:
    """挑最突出的最多三处：{"group": [只在群里提醒的], "all": [哪里都提醒的]}"""
    group, every = [], []
    if stats["group_short"] >= 15 and (stats["group_short_median"] > 15 or stats["group_short_multi"] >= 30):
        group.append(f"最近群里别人只说几个字，你常回 {stats['group_short_median']:.0f} 字左右、"
                     f"{stats['group_short_multi']}% 拆成好几条，收着点，一条就够")
    if stats["group_actions"] >= 3:
        group.append(f"最近群里写了 {stats['group_actions']} 次括号动作，群里别写")
    n = max(stats["replies"], 1)
    for word, k in stats["openers"][:1]:  # 900 条里「行」开头 26 次（约 3%）就已经很显眼
        if k >= 8 and k * 1000 // n >= 25:
            every.append(f"开头最近老用「{word}」（{k} 次），换着说，或者直接说事")
    for phrase, k in stats["phrases"][:1]:
        if k >= 12 and k * 1000 // n >= 12:
            every.append(f"「{phrase}」最近说了 {k} 次，先放一放")
    notes = (group + every)[:3]
    return {"group": [x for x in group if x in notes], "all": [x for x in every if x in notes]}


class HabitCheck:
    def __init__(self, cfg: dict, db_path: str, notes_path: str):
        # 工具箱「habit_check」一节：{"run_at": "04:30", "recent_per_chat": 40}
        self.run_at = str(cfg.get("run_at", "04:30")).strip() or "04:30"
        self.recent_per_chat = max(5, int(cfg.get("recent_per_chat", 40)))
        self.db_path, self.notes_path = db_path, notes_path
        self.notes = self._load()
        self.task: asyncio.Task | None = None
        logger.info(f"[habit_check] 每天 {self.run_at} 自检说话习惯；现在的提醒：{self._summary()}")

    def _summary(self) -> str:
        lines = self.notes.get("group", []) + self.notes.get("all", [])
        return f"{self.notes.get('date', '还没算过')}，{len(lines)} 条" if self.notes else "还没算过"

    def _load(self) -> dict:
        try:
            with open(self.notes_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[habit_check] 提醒文件读不了，重算：{e}")
            return {}

    def collect(self) -> list[dict]:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
        try:
            rows = con.execute("select user_id, content from conversations").fetchall()
        finally:
            con.close()
        out = []
        for uid, content in rows:
            try:
                history = json.loads(content) if isinstance(content, str) else content
            except Exception:  # noqa: BLE001
                continue
            out += replies_of(history, "GroupMessage" in str(uid), self.recent_per_chat)
        return out

    def refresh(self) -> dict:
        stats = analyze(self.collect())
        notes = make_notes(stats)
        self.notes = {"date": datetime.datetime.now(TZ).date().isoformat(), "stats": stats, **notes}
        os.makedirs(os.path.dirname(self.notes_path), exist_ok=True)
        tmp = self.notes_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.notes, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.notes_path)
        logger.info(f"[habit_check] 按最近 {stats['replies']} 条回复重算：{notes['group'] + notes['all'] or '没有突出的小毛病'}")
        return self.notes

    def _seconds_to_next_run(self, now: datetime.datetime) -> float:
        hour, _, minute = self.run_at.partition(":")
        target = now.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return (target - now).total_seconds()

    async def _loop(self) -> None:
        if self.notes.get("date") != datetime.datetime.now(TZ).date().isoformat():
            await self._refresh_safely()
        while True:
            await asyncio.sleep(self._seconds_to_next_run(datetime.datetime.now(TZ)))
            await self._refresh_safely()

    async def _refresh_safely(self) -> None:
        try:
            await asyncio.to_thread(self.refresh)
        except Exception as e:  # noqa: BLE001 - 算不出来就沿用旧提醒，明天再算
            logger.warning(f"[habit_check] 这次没算出来，先用旧提醒：{e}")

    def start(self) -> None:
        """在 AstrBot 的事件循环里挂上每日自检；没有在跑的循环（比如测试里）就不挂"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self.task is None:
            self.task = loop.create_task(self._loop())

    def terminate(self) -> None:
        if self.task is not None:
            self.task.cancel()
            self.task = None

    def hint_for(self, event: AstrMessageEvent) -> str:
        if not event.is_at_or_wake_command or getattr(event, "private_companion_proactive_framework", False):
            return ""
        lines = (self.notes.get("group", []) if event.get_group_id() else []) + self.notes.get("all", [])
        return "【最近说话的小毛病】" + "；".join(lines) + "。" if lines else ""

    async def add_hint(self, event: AstrMessageEvent, req) -> bool:
        """main.py 在 on_llm_request 接上"""
        hint = self.hint_for(event)
        if not hint:
            return False
        if not isinstance(getattr(req, "extra_user_content_parts", None), list):
            req.extra_user_content_parts = []
        req.extra_user_content_parts.append(TextPart(text=hint).mark_as_temp())
        return True
