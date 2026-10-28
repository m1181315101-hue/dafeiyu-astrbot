# 翻唱 / 变声服务

跑在 Mac 本机（Apple GPU）的小服务，给 `astrbot_plugin_sing`（唱歌）和 `astrbot_plugin_voice`（说话变声）用：

- `POST /cover`：找歌 → 挑一段副歌 → Demucs 分离人声 → RVC 换成她的声音 → 混回伴奏 → 返回 mp3
- `POST /convert`：把 TTS 念出来的说话声换成她的声音
- `GET /health`：服务状态、当前模型、是否忙

只监听 127.0.0.1，请求头 `X-Token` 校验。安装、模型、网易云来源和参数说明见 [`docs/本机部署-macOS.md`](../../docs/本机部署-macOS.md)。

```bash
uv venv -p 3.10 .venv && uv pip install -p .venv/bin/python -r requirements.txt
cp config.example.json config.json   # 填 token
./start.sh                           # ./stop.sh 停止，日志 server.log
```

仓库不带声音模型、网易云登录态和任何缓存的歌；这些都在 `.gitignore` 里，别提交。
