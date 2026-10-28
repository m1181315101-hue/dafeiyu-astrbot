"""大肥鱼翻唱服务：跑在 Mac 本机（用 Apple GPU），AstrBot 的 sing_song 工具从容器里调它。

/convert：把 TTS 念出来的说话声换成她的声音。
/cover 流程：找歌（链接 → songs/ 曲库 → 网易云（登录了才用）→ AnySearch 搜 B 站链接再下载）→ 挑一段最响的（多半是副歌）→ Demucs 分离人声和伴奏
→ RVC 把人声换成她的声音 → 和伴奏混回去 → 返回 mp3。

只监听 127.0.0.1；容器经 host.docker.internal 访问。配置在同目录 config.json，改完重启服务。
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# RVC 在本进程里跑 torch，MPS 没实现的算子退回 CPU，而不是直接报错（要在 import torch 之前设）
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
MODELS_DIR = os.path.join(ROOT, "models")
SONGS_DIR = os.path.join(ROOT, "songs")
CACHE_DIR = os.path.join(ROOT, "cache")
SR = 44100
AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus")
# 搜索结果里这些标题多半不是原曲
BAD_TITLE_RE = re.compile(r"伴奏|教学|教程|钢琴|吉他|翻唱|cover|remix|dj|合集|串烧|循环|小时|reaction|解说|片段|铃声", re.I)
# 网易云上别人的翻唱会在歌名里写“原唱 XX”“翻自 XX”，歌手名混在歌名里会骗过按词匹配
NCM_COVER_RE = re.compile(r"原唱|翻自")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(os.path.join(ROOT, "server.log"), encoding="utf-8")],
)
log = logging.getLogger("cover")
app = FastAPI()
lock = asyncio.Lock()
_rvc = None  # (模型名, RVCInference)


class CoverRequest(BaseModel):
    query: str
    # 只给本机测试用：没有模型时直接用原唱人声走完流程
    passthrough: bool = False


def run(cmd: list[str], timeout: int) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{os.path.basename(cmd[0])} 失败：{(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout


def current_model() -> str | None:
    """config.json 的 model 指定 models/ 下的子目录；留空就用唯一的那个"""
    names = sorted(d for d in os.listdir(MODELS_DIR) if os.path.isdir(os.path.join(MODELS_DIR, d))
                   and any(f.endswith(".pth") for f in os.listdir(os.path.join(MODELS_DIR, d))))
    want = CFG.get("model") or ""
    if want:
        return want if want in names else None
    return names[0] if len(names) == 1 else None


def find_local_song(query: str) -> str | None:
    words = [w.lower() for w in query.split() if w]
    for f in sorted(os.listdir(SONGS_DIR)):
        if f.lower().endswith(AUDIO_EXT) and all(w in f.lower() for w in words):
            return os.path.join(SONGS_DIR, f)
    return None


def probe(url: str) -> tuple[str, float, str] | None:
    """用 yt-dlp 读单个视频的 (id, 时长, 标题)"""
    try:
        out = run([CFG["yt_dlp"], "--skip-download", "--no-warnings", "--no-playlist", "--print",
                   "%(id)s\t%(duration)s\t%(title)s", url], timeout=60)
        vid, dur, title = out.strip().splitlines()[0].split("\t", 2)
        return vid, float(dur), title
    except Exception as e:
        log.info("读取视频信息失败 %s：%s", url, e)
        return None


def search_web(query: str) -> tuple[str, str, str]:
    """用 AnySearch（和 AstrBot 联网搜索同一个，匿名）找 B 站视频链接，挑时长合适、标题不像伴奏/翻唱/合集的第一个。
    返回 (视频 id, 标题, 链接)"""
    import urllib.request
    # 搜到过的歌记下来，再点同一首不用重新搜（搜索结果时有时无）
    found_path = os.path.join(CACHE_DIR, "found.json")
    try:
        found = json.load(open(found_path, encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    key = " ".join(query.lower().split())
    if key in found:
        return tuple(found[key])
    tried = []
    for q in (f"{query} bilibili", f"{query} MV bilibili"):
        body = json.dumps({"query": q, "max_results": 10}).encode()
        req = urllib.request.Request("https://api.anysearch.com/v1/search", data=body,
                                     headers={"Content-Type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=30))
        urls = []
        for it in (data.get("data") or data).get("results", []):
            m = re.search(r"https?://(?:www\.|m\.)?bilibili\.com/video/(?:BV\w+|av\d+)", it.get("url", ""))
            if m and m.group(0) not in urls + tried and not BAD_TITLE_RE.search(it.get("title", "")):
                urls.append(m.group(0))
        log.info("搜索 %s：%d 个 B 站候选", q, len(urls))
        for url in urls[:4]:
            tried.append(url)
            meta = probe(url)
            if meta and 60 <= meta[1] <= CFG["max_song_seconds"] and not BAD_TITLE_RE.search(meta[2]):
                found[key] = [meta[0], meta[2], url]
                with open(found_path, "w", encoding="utf-8") as f:
                    json.dump(found, f, ensure_ascii=False, indent=1)
                return meta[0], meta[2], url
    raise RuntimeError("没搜到合适的版本")


NCM_COOKIE = os.path.join(ROOT, "ncm_cookie.txt")


def ncm_call(path: str, **params) -> dict:
    """调本机的网易云接口（ncm-api 容器）；cookie 放在 POST 正文里，不进 URL"""
    import urllib.parse
    import urllib.request
    if os.path.exists(NCM_COOKIE):
        params["cookie"] = open(NCM_COOKIE, encoding="utf-8").read().strip()
    # 接口按 URL 缓存 2 分钟，时间戳要放在 URL 上才拿得到新结果
    url = f"{CFG.get('ncm_api', 'http://127.0.0.1:3000')}{path}?timestamp={int(time.time() * 1000)}"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST")
    return json.load(urllib.request.urlopen(req, timeout=20))


def search_netease(query: str) -> tuple[str, str, str] | None:
    """网易云找歌。歌名（去掉括号里的备注）必须正好是点的那首，点歌里剩下的字必须是这首歌的歌手，
    比如“晴天 周杰伦”只认周杰伦唱的《晴天》，不认歌名里带“周杰伦”的翻唱和 beat；只点歌名就不限歌手。
    能拿到完整音频（不是 30 秒试听）才算。没登录、接口没开、没找到都返回 None，交给 B 站兜底。
    返回 (本地文件, “歌名 - 歌手”, ncm-歌曲id)"""
    if not os.path.exists(NCM_COOKIE):
        return None
    try:
        songs = (ncm_call("/cloudsearch", keywords=query, type=1, limit=15).get("result") or {}).get("songs") or []
        q = re.sub(r"\s+", "", query).lower()
        for s in songs:
            name = s.get("name", "")
            artists = "、".join(a.get("name", "") for a in s.get("ar", []))
            core = re.sub(r"\s+", "", re.sub(r"[(（\[【].*?[)）\]】]", "", name)).lower()
            rest = q.replace(core, "", 1) if core and core in q else None
            artist_ok = rest == "" or (rest is not None and rest in re.sub(r"\s+", "", artists).lower())
            dur = s.get("dt", 0) / 1000
            if (not artist_ok or BAD_TITLE_RE.search(name) or NCM_COVER_RE.search(name)
                    or not 60 <= dur <= CFG["max_song_seconds"]):
                continue
            sid = f"ncm-{s['id']}"
            dst = os.path.join(CACHE_DIR, "downloads", f"{sid}.mp3")
            if not os.path.exists(dst):
                d = (ncm_call("/song/url/v1", id=s["id"], level="exhigh").get("data") or [{}])[0]
                if not d.get("url") or d.get("freeTrialInfo"):
                    log.info("网易云 %s - %s 拿不到完整音频（版权/试听）", name, artists)
                    continue
                import urllib.request
                urllib.request.urlretrieve(d["url"], dst + ".part")
                os.replace(dst + ".part", dst)
            log.info("网易云命中 %s - %s（%s）", name, artists, sid)
            return dst, f"{name} - {artists}", sid
        log.info("网易云没有合适的：%s", query)
    except Exception as e:
        log.info("网易云不可用，改走 B 站：%s", e)
    return None


def download(vid: str, url: str) -> str:
    dl_dir = os.path.join(CACHE_DIR, "downloads")
    hit = [f for f in os.listdir(dl_dir) if f.startswith(vid + ".") and not f.endswith(".part")]
    if hit:
        return os.path.join(dl_dir, hit[0])
    run([CFG["yt_dlp"], "-f", "ba/b", "--no-playlist", "--no-warnings", "-o",
         os.path.join(dl_dir, f"{vid}.%(ext)s"), url], timeout=300)
    hit = [f for f in os.listdir(dl_dir) if f.startswith(vid + ".") and not f.endswith(".part")]
    if not hit:
        raise RuntimeError("下载失败")
    return os.path.join(dl_dir, hit[0])


def to_wav(src: str, dst: str) -> None:
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "2", "-ar", str(SR), dst], timeout=120)


def pick_clip(wav: str) -> tuple[float, float]:
    """在整首歌里找 clip_seconds 长、平均响度最高的一段（跳过开头 10% 和结尾 15%）"""
    a, sr = sf.read(wav, dtype="float32")
    mono = a.mean(axis=1) if a.ndim == 2 else a
    total = len(mono) / sr
    clip = min(float(CFG["clip_seconds"]), total)
    hop = sr // 2  # 0.5 秒一格
    rms = np.array([np.sqrt(np.mean(mono[i:i + hop] ** 2) + 1e-12) for i in range(0, len(mono) - hop, hop)])
    n = int(clip * 2)
    if len(rms) <= n:
        return 0.0, clip
    lo, hi = int(len(rms) * 0.10), int(len(rms) * 0.85) - n
    if hi <= lo:
        lo, hi = 0, len(rms) - n
    window = np.convolve(rms, np.ones(n), "valid")
    best = lo + int(np.argmax(window[lo:hi + 1]))
    return best / 2, clip


def cut(src: str, dst: str, start: float, dur: float) -> None:
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", src,
         "-ac", "2", "-ar", str(SR), dst], timeout=120)


def separate(wav: str, out_dir: str) -> tuple[str, str]:
    env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1")
    r = subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs",
                        "-d", "mps", "-o", out_dir, wav], capture_output=True, text=True, timeout=600, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"人声分离失败：{r.stderr.strip()[-300:]}")
    stem_dir = os.path.join(out_dir, "htdemucs", os.path.splitext(os.path.basename(wav))[0])
    return os.path.join(stem_dir, "vocals.wav"), os.path.join(stem_dir, "no_vocals.wav")


def median_f0(wav: str) -> float | None:
    import librosa
    y, sr = librosa.load(wav, sr=16000, mono=True)
    f0 = librosa.yin(y, fmin=70, fmax=1000, sr=sr)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0][: len(f0)]
    voiced = f0[: len(rms)][rms > max(rms.max() * 0.1, 1e-4)]
    return float(np.median(voiced)) if len(voiced) else None


def octave_shift(vocals: str) -> int:
    """只按整八度升降（0 / ±12），伴奏不变调也不跑调"""
    key = CFG.get("f0_up_key", "auto")
    if key != "auto":
        return int(key)
    f0 = median_f0(vocals)
    if not f0:
        return 0
    target = float(CFG["target_f0_hz"])
    return min((-12, 0, 12), key=lambda k: abs(math.log2(f0 * 2 ** (k / 12) / target)))


def clean_f0(f0: np.ndarray) -> np.ndarray:
    """RMVPE 音高的小修（每秒 100 帧）：
    1. 音符中间极短的没音高（≤ f0_fill_gap_frames 帧）补上，不然那一下会变成嘶哑气声；
    2. 和前后约 0.15 秒的中位数差 9 个半音以上的帧，按整八度拉回来，不然就是一下破音。"""
    f0 = np.asarray(f0, dtype=np.float64).copy()
    n = len(f0)
    gap = int(CFG.get("f0_fill_gap_frames", 4))
    voiced = f0 > 0
    i = 0
    while i < n:
        if voiced[i]:
            i += 1
            continue
        j = i
        while j < n and not voiced[j]:
            j += 1
        if i > 0 and j < n and j - i <= gap:
            f0[i:j] = 2 ** np.linspace(np.log2(f0[i - 1]), np.log2(f0[j]), j - i + 2)[1:-1]
        i = j
    voiced = f0 > 0
    semis = np.full(n, np.nan)
    semis[voiced] = 12 * np.log2(f0[voiced])
    win = 15
    for k in np.flatnonzero(voiced):
        d = semis[k] - np.nanmedian(semis[max(0, k - win):k + win + 1])
        if abs(d) >= 9:
            f0[k] *= 2 ** -np.round(d / 12)
    return f0


def _patch_rmvpe() -> None:
    """在 RMVPE 提完音高、RVC 合成之前插一道 clean_f0（config 里 f0_cleanup=false 就不插）"""
    from rvc_python.lib.rmvpe import RMVPE
    if not CFG.get("f0_cleanup", True) or getattr(RMVPE.infer_from_audio, "_cleaned", False):
        return
    orig = RMVPE.infer_from_audio

    def infer_from_audio(self, audio, thred=0.03):
        return clean_f0(orig(self, audio, thred)).astype(np.float32)

    infer_from_audio._cleaned = True
    RMVPE.infer_from_audio = infer_from_audio


def convert(model: str, vocals: str, dst: str, shift: int) -> None:
    global _rvc
    if _rvc is None or _rvc[0] != model:
        import torch
        from fairseq.data.dictionary import Dictionary
        from rvc_python.infer import RVCInference

        # PyTorch 2.6+ 默认只读权重加载；hubert_base.pt 里多引用了 fairseq 的 Dictionary（只是词表），
        # 只放行这一个类，其余仍按安全模式加载
        torch.serialization.add_safe_globals([Dictionary])
        _patch_rmvpe()
        r = RVCInference(models_dir=MODELS_DIR)
        r.load_model(model, version=CFG.get("rvc_version", "v2"))
        _rvc = (model, r)
    r = _rvc[1]
    r.set_params(f0up_key=shift, f0method="rmvpe", index_rate=CFG["index_rate"], protect=CFG["protect"])
    r.infer_file(vocals, dst)


def mix(vocals: str, accomp: str, dst: str, dur: float) -> None:
    fade = 0.8
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", vocals, "-i", accomp, "-filter_complex",
         f"[0:a]aresample={SR},aformat=channel_layouts=stereo,volume={CFG['vocal_gain_db']}dB[v];"
         f"[1:a]aresample={SR},aformat=channel_layouts=stereo,volume={CFG.get('accomp_gain_db', 0)}dB[m];"
         f"[v][m]amix=inputs=2:duration=longest:normalize=0,"
         # QQ 语音条本来就是 24k 单声道；AstrBot 发之前还会转成 wav，立体声 44.1k 会大到 7MB。
         # 先降成单声道再统一响度（反过来会因为左右抵消小 3dB）；loudnorm 输出 192k，要再降回 24k，
         # 重采样后峰值会反弹，最后压一道限幅（-2dB），给 mp3 编码留余量，免得破音
         f"afade=t=in:d={fade},afade=t=out:st={max(dur - fade, 0):.2f}:d={fade},pan=mono|c0=0.5*c0+0.5*c1,"
         f"loudnorm=I={CFG.get('loudness_lufs', -11)}:TP=-1,aresample=24000,alimiter=limit=0.79:level=false",
         "-b:a", "64k", dst], timeout=180)


def make_cover(query: str, passthrough: bool) -> tuple[str, dict]:
    model = current_model()
    if model is None and not passthrough:
        raise HTTPException(409, "no_model")
    link = re.search(r"https?://\S+", query)
    local = None if link else find_local_song(query)
    ncm = None if link or local else search_netease(query)
    if local:
        src, title, source = local, os.path.splitext(os.path.basename(local))[0], "曲库"
        src_id = "local-" + hashlib.sha1(local.encode()).hexdigest()[:12]
    elif ncm:
        src, title, src_id = ncm
        source = "网易云 " + src_id
    else:
        if link:
            meta = probe(link.group(0))
            if not meta:
                raise RuntimeError("这个链接读不出来")
            if meta[1] > CFG["max_song_seconds"]:
                raise RuntimeError("这个视频太长了，不像一首歌")
            (vid, _, title), url = meta, link.group(0)
        else:
            vid, title, url = search_web(query)
        src, source, src_id = download(vid, url), url, vid
    # 影响成品的参数都进缓存键，调完参数不会拿到旧结果
    params = [CFG.get(k) for k in ("f0_up_key", "target_f0_hz", "clip_seconds", "index_rate", "protect", "vocal_gain_db", "accomp_gain_db", "loudness_lufs", "f0_cleanup", "f0_fill_gap_frames")]
    key = hashlib.sha1(json.dumps([src_id, model, passthrough, params]).encode()).hexdigest()[:16]
    out = os.path.join(CACHE_DIR, "results", f"{key}.mp3")
    info = {"title": title, "source": source, "model": model or "（没有模型，原唱人声）"}
    if os.path.exists(out):
        info["cached"] = True
        return out, info
    work = tempfile.mkdtemp(prefix="cover-", dir=os.path.join(CACHE_DIR, "work"))
    try:
        full = os.path.join(work, "full.wav")
        to_wav(src, full)
        start, dur = pick_clip(full)
        clip = os.path.join(work, "clip.wav")
        cut(full, clip, start, dur)
        t0 = time.time()
        vocals, accomp = separate(clip, work)
        info["separate_s"] = round(time.time() - t0, 1)
        if model:
            t0 = time.time()
            shift = octave_shift(vocals)
            converted = os.path.join(work, "converted.wav")
            convert(model, vocals, converted, shift)
            info.update(rvc_s=round(time.time() - t0, 1), shift=shift)
        else:
            converted = vocals
        mix(converted, accomp, out, dur)
        info.update(start=round(start, 1), seconds=round(dur, 1))
        return out, info
    finally:
        shutil.rmtree(work, ignore_errors=True)


def convert_speech(model: str, data: bytes) -> bytes:
    """说话变声：TTS 念出来的音频 → RVC 换成她的声音 → 24k 单声道 wav"""
    work = tempfile.mkdtemp(prefix="speech-", dir=os.path.join(CACHE_DIR, "work"))
    try:
        src, wav = os.path.join(work, "in"), os.path.join(work, "in.wav")
        with open(src, "wb") as f:
            f.write(data)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(SR), wav], timeout=60)
        conv, out = os.path.join(work, "conv.wav"), os.path.join(work, "out.wav")
        # 晓伊本来就是女声，说话默认不升降调
        convert(model, wav, conv, int(CFG.get("speech_f0_up_key", 0)))
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", conv, "-af", f"loudnorm=I={CFG.get('loudness_lufs', -11)}:TP=-1",
             "-ac", "1", "-ar", "24000", out], timeout=60)
        with open(out, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def check_token(token: str | None) -> None:
    if CFG.get("token") and token != CFG["token"]:
        raise HTTPException(401, "bad token")


@app.get("/health")
async def health(x_token: str | None = Header(default=None)):
    check_token(x_token)
    return {"ok": True, "model": current_model(), "busy": lock.locked()}


@app.post("/cover")
async def cover(req: CoverRequest, x_token: str | None = Header(default=None)):
    check_token(x_token)
    query = req.query.strip()[:200]
    if not query:
        raise HTTPException(400, "empty query")
    if lock.locked():
        raise HTTPException(429, "busy")
    async with lock:
        t0 = time.time()
        try:
            path, info = await asyncio.to_thread(make_cover, query, req.passthrough)
        except HTTPException:
            raise
        except Exception as e:
            log.exception("翻唱失败：%s", query)
            raise HTTPException(500, str(e)[:300])
        info["total_s"] = round(time.time() - t0, 1)
        log.info("翻唱完成 %s -> %s", query, info)
        data = open(path, "rb").read()
    return Response(data, media_type="audio/mpeg",
                    headers={"X-Cover-Info": json.dumps(info, ensure_ascii=True)})


@app.post("/convert")
async def convert_voice(request: Request, x_token: str | None = Header(default=None)):
    """请求体是一段音频（任意 ffmpeg 能读的格式），返回换成她声音的 wav；正在翻唱时直接 429，调用方退回原声"""
    check_token(x_token)
    model = current_model()
    if model is None:
        raise HTTPException(409, "no_model")
    if lock.locked():
        raise HTTPException(429, "busy")
    data = await request.body()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "bad audio")
    async with lock:
        t0 = time.time()
        try:
            out = await asyncio.to_thread(convert_speech, model, data)
        except Exception as e:
            log.exception("说话变声失败")
            raise HTTPException(500, str(e)[:300])
    log.info("说话变声完成 %.1f 秒，%d 字节", time.time() - t0, len(out))
    return Response(out, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    for d in (MODELS_DIR, SONGS_DIR, *(os.path.join(CACHE_DIR, x) for x in ("downloads", "results", "work"))):
        os.makedirs(d, exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=int(CFG["port"]), log_level="warning")
