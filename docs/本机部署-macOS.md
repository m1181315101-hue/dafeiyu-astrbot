# 大肥鱼 · 本机部署（macOS / Docker Desktop）

在一台 Mac 上用 Docker 跑两个容器，另在 Mac 本机跑一个翻唱 / 变声服务（用 Apple GPU）：

- **napcat**：登录一个 QQ 号，把消息转给 AstrBot。这一版是按**挂在主人自己的号上**写的（不是小号），配套人格见 `persona/大肥鱼-人格-本机版.md`
- **astrbot**：大肥鱼的大脑，加载人格和插件，调用 DeepSeek 回复
- **翻唱服务**（`deploy/cover/`，可选）：让她用自己的声音唱歌、把说话声换成她的声音

所有端口都只绑在本机（127.0.0.1），局域网和外网都连不进来。

和云端版（`deploy/README.md`）的区别：数据目录用相对路径；不挂百炼语音补丁；语音改用免费的 edge-tts，再用 RVC 换成她的声音；多了群聊续聊、只回指定群、唱歌三个插件。

## 目录

找一个工作目录（下面叫 `dafeiyu/`），按这样摆：

```
dafeiyu/
├── compose.yaml        ← 复制自仓库 deploy/mac/compose.yaml
├── astrbot/data/       ← AstrBot 的配置、数据库、插件（首次启动自动生成；含 API key，别外传）
│   └── plugins/        ← 把仓库 plugin/ 下要用的插件目录复制进来
├── cover/              ← 复制自仓库 deploy/cover/（翻唱服务，跑在 Mac 本机，不在 Docker 里）
├── ncm-api/            ← 网易云接口容器的代码，首次启动自动 npm 安装（可选）
└── napcat/             ← NapCat 配置和 QQ 登录态（首次启动自动生成；别外传）
```

```bash
docker compose up -d          # 在 dafeiyu/ 里执行，起 astrbot 和 napcat
```

- 改 `compose.yaml` 后才需要 `docker compose up -d`，它会重建容器，NapCat 可能要重新扫码。
- 只是重启的话用 `docker restart napcat` / `docker restart astrbot`。
- 如果 AstrBot 重启后她不回消息了，多半是 NapCat 的 WebSocket 没重连：`docker restart napcat`。

## 首次配置

1. **扫码登录**：打开 http://127.0.0.1:6099 ，用要挂她的那个号的手机 QQ 扫码。
   WebUI 的登录 token 在日志里：`docker logs napcat 2>&1 | grep -i token`
2. **登录 AstrBot 面板**：打开 http://127.0.0.1:6185 ，用户名 `astrbot`，
   初始密码在日志里：`docker logs astrbot 2>&1 | grep -A1 'Initial username'`。登录后先改密码。
3. **填 DeepSeek key**：模型提供商 → 新增 → 选「DeepSeek」（不是 DeepSeek Responses）→
   填 API Key → 加上模型 `deepseek-chat`。对话模型留空就会用它。
4. **人格**：把 `persona/大肥鱼-人格-本机版.md` 里的 `{主人}`、`{主人别名}`、`{主人小号QQ}` 换成自己的，
   `---` 之后的正文整段粘贴到面板「人格管理」，设为默认人格。改完要 `docker restart astrbot` 才生效。
5. **插件**：把要用的插件目录复制到 `astrbot/data/plugins/`，每个插件把 `config.example.json` 复制成 `config.json` 再改，
   改完 `docker restart astrbot`。没有 `config.json` 时插件用代码里的默认值（token 为空）。
6. **（可选）白名单**：只想让部分人能聊时再设。白名单为空 = 不启用。
   会话 ID 形如 `default:FriendMessage:对方QQ号`（对方私聊她发 `/sid` 也能拿到），
   填进 配置文件 → 访问控制 → 白名单，**记得点保存**。
   不要把群号填进白名单：白名单一旦非空，没列进去的私聊就全被拦了。只回指定的群用下面的 `astrbot_plugin_private_only`。

NapCat 用 `MODE=astrbot` 启动，会自动生成 OneBot v11 反向 WebSocket 配置，连到 `ws://astrbot:6199/ws`。

## AstrBot 配置（`astrbot/data/cmd_config.json`）

这几项在面板里也能改，这里列出本机版用的值：

- **分段回复** `platform_settings.segmented_reply`：她回复里**每一行单独发一条**，代码块整块发；长回复整条发不拆；
  每条末尾的句号去掉；每条发之前按字数等一会儿，像在打字。QQ 表情会单独成一条跟在文字后面。
  ```json
  "enable": true,
  "regex": "```.*?```|[^\\n]+",
  "words_count_threshold": 240,
  "interval_method": "log",
  "content_cleanup_rule": "。+\\s*$"
  ```
- **发送者信息** `provider_settings.identifier=true`：每条消息都告诉她对方的 QQ 号和昵称（人格靠这个分清谁在说话）。
- **联网搜索** `provider_settings.web_search=true`、`websearch_provider="anysearch"`，**不填 key 匿名用**。
  匿名额度官方没写，哪天搜不动了，可以申请 AnySearch key 填到 `websearch_anysearch_key`，或者换成 Tavily。
- **TTS 提供商**：新增 edge_tts，id 填 `edge_tts`，声音 `zh-CN-XiaoyiNeural`（晓伊），其余默认。
  `provider_tts_settings.enable=false`（关掉“按概率把回复变成语音”，只在有人要时发，见 `astrbot_plugin_voice`）。
- NapCat 的 `reportSelfMessage` 保持关闭：挂在主人自己的号上时，**主人自己发的消息她看不到**，
  所以主人没法用这个号跟她聊。打开它的话，主人跟朋友私聊时她也会插嘴。想自己跟她聊，得用另一个 QQ 号。

官方 AstrBot 镜像里没有 edge-tts，装到持久目录（重建容器也在）：

```bash
docker exec astrbot pip install --no-deps --target /AstrBot/data/site-packages edge-tts srt tabulate
```

## 插件

完整清单（含第三方插件的来源、版本、启用状态）和改过的配置项见 [`deploy/mac/config/`](../deploy/mac/config/README.md)。
目前群聊续聊、生活日程和主动消息交给第三方的陪伴插件 `astrbot_plugin_private_companion`，下面的 `astrbot_plugin_group_followup` 已停用（留着备用）。

- `astrbot_plugin_face_convert`：把 `[旺柴]` 这类写法变成真 QQ 表情（见 README）。
- `astrbot_plugin_private_only`：**私聊都回，群里只回指定的群**。
  - 允许的群写在 `config.json`：`{"allowed_groups": ["群号", ...]}`，空列表 = 群里都不回。
  - 其他群的消息在最前面就被拦下，@ 她、发指令都不回；有人唤醒她时日志会记一行 `[private_only] 群里有人唤醒她，已忽略`。
  - 在允许的群里，这些情况会唤醒她：**@ 她**、引用她的消息、消息以 `/` 或唤醒词开头（`cmd_config.json` 的 `wake_prefix`）。
    `@全体成员` 默认也会唤醒她（`platform_settings.ignore_at_all=false`）。
  - 想所有群都能回，不装这个插件。
- `astrbot_plugin_group_followup`：**群聊续聊，不用每句都 @**。
  - 谁唤醒了她（@、引用、喊唤醒词），接下来**只有这个人**不用 @ 也能接着聊，别人插话还是要 @。
  - 这些情况结束续聊，之后要重新 @：她最后一次回复后 3 分钟没人接；对方说“拜拜/晚安/去忙了”之类（这句她照回）；
    对方 @ 了别人或引用了别人的消息；她判断这条不是跟她说的（输出 `[NO_REPLY]`，不回）；连续 8 条没 @。
  - 时长和条数：`{"window_seconds": 180, "max_followups": 8}`。
  - 日志里 `[group_followup] 结束续聊 群号/QQ号：原因` 能看到每次为什么结束。
- `astrbot_plugin_voice`：**有人要她发语音时才发**。给她一个 `tts_speak` 工具，念完发成 QQ 语音条；
  - `[旺柴]` 这类表情标记不念。**用语音回答的那一轮只发语音、不再发文字**。每条最多 200 字（约 45 秒，超了在句号处截断，`max_chars`）。
  - **说话也是她的声音**：edge-tts 念完后送去翻唱服务的 `/convert`，用 RVC 换成和唱歌同一个声音。
    **翻唱服务没开、正在翻唱别的歌、或者变声失败时，直接发晓伊原声**，不会发不出去。
    `rvc_url` 默认 `http://host.docker.internal:8790`，`rvc_token` 要和 `cover/config.json` 的 `token` 一样。
    日志里每条会写用的是“RVC 声音”还是“TTS 原声（原因）”。
  - **音量**：发出去前统一拉到约 -12 LUFS、峰值压在 -1dB（`loudness_lufs`，默认 -11）。晓伊原声只有 -22 左右，偏小。
  - AstrBot 4.29 自带的 edge_tts 提供商会把 User-Agent 换掉，导致微软回 403；插件每次发语音前会把它改回来。
  - 实测（M4）一句 30 字：变声后 3.7 秒发出（服务刚启动后的第一条要加载模型，约 10 秒）；退回晓伊 2.3 秒。
- `astrbot_plugin_sing`：有人让她唱歌时调 `sing_song` 工具，请求翻唱服务，一两分钟后发来一段语音条。
  服务没开、没有模型、正在唱别的歌时，她会如实说。`token` 要和 `cover/config.json` 的一样。

## 翻唱服务（`cover/`）

### 安装

```bash
brew install ffmpeg yt-dlp
cd dafeiyu/cover
uv venv -p 3.10 .venv
uv pip install -p .venv/bin/python -r requirements.txt
cp config.example.json config.json
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # 生成 token，填进 config.json 的 token，以及两个插件的 token / rvc_token
```

- 首次加载 RVC 时 rvc-python 会自动下载 hubert、rmvpe 基础模型到它的包目录。
- `config.json` 的 `yt_dlp` 是 yt-dlp 的路径（Homebrew 默认 `/opt/homebrew/bin/yt-dlp`）。
- 服务只监听 127.0.0.1:8790，容器经 `host.docker.internal` 访问；`token` 为空时不校验，建议一定填上。

### 启动 / 停止

`cover/start.sh`、`cover/stop.sh`（连网易云接口容器一起启停），日志 `cover/server.log`。
不设开机自启，要用的时候手动 start。

### 声音模型

仓库**不带**模型。自己准备一个 RVC 模型，放成 `cover/models/<名字>/<名字>.pth`（有 `.index` 也放进去）。
models 下只有一个时自动用它，多个就在 `config.json` 的 `model` 写文件夹名；然后 `cover/stop.sh && cover/start.sh`。

- 先确认模型是 v1 还是 v2（看权重 `enc_p.emb_phone` 的输入维度：256 是 v1，768 是 v2），写进 `rvc_version`。
  例：BOOTH 上的免费模型「NORA」（https://booth.pm/ja/items/4706454 ）页面写 RVCv2，文件实际是 v1。
  用别人的模型要看清条款（NORA：非商用免费、允许翻唱、禁止再分发，能署名时写上），**模型文件不要传进仓库**。
- 新拿到的 `.pth` 先用 `torch.load(..., weights_only=True)` 检查，能加载再用：`.pth` 是 pickle，恶意文件加载时能执行代码。
- PyTorch 2.6+ 默认只读权重加载，RVC 的 `hubert_base.pt` 里引用了 fairseq 的 `Dictionary`，
  服务里只放行了这一个类（`server.py` 的 `convert()`），其它照旧安全加载。

### 流程

找歌 → 挑一段最响的 40 秒（多半是副歌）→ Demucs 分离人声和伴奏 → RVC 把人声换成她的声音
（按整八度自动升降，伴奏不变调）→ 混回去 → 24k 单声道 mp3 → 发成语音条。
实测（M4）一段 40 秒副歌从搜歌到出 mp3 约 27 秒（分离 6 秒、RVC 14 秒）。

**歌从哪来**（按顺序）：
1. 对方给的链接
2. `cover/songs/` 里文件名包含歌名的音频（可以自己往里放）
3. 网易云（登录了才用，见下）
4. 用 AnySearch 搜 B 站链接再用 yt-dlp 下载（搜到过的记在 `cover/cache/found.json`）。B 站自带的搜索接口会拦脚本（412），所以不用它。

下载的整首歌缓存在 `cover/cache/downloads/`，做好的翻唱缓存在 `cover/cache/results/`。

### 网易云来源（可选）

- 接口是社区逆向的 `@neteasecloudmusicapienhanced/api@4.41.1`（MIT），跑在 `ncm-api` 容器里（`compose.yaml` 的
  `cover` profile，只绑 127.0.0.1:3000，代码装在 `ncm-api/`）。`docker compose up/start` 不会带它；
  第一次在 `dafeiyu/` 里执行 `docker compose --profile cover up -d ncm-api` 建好容器，以后跟着 `cover/start.sh`、`stop.sh` 启停。
  “灰色歌曲从其他平台补全”的解锁功能是关的（`ENABLE_GENERAL_UNBLOCK=false`，也从不传 `unblock=true`）。
- 登录：`cd cover && .venv/bin/python ncm_login.py`，用网易云 App 扫生成的 `ncm-login-qr.png`。
  登录态存在 `cover/ncm_cookie.txt`（权限 600，**等同于账号登录，别外传**）。删掉这个文件 = 不用网易云。
  完整音频一般要黑胶 VIP。
- 匹配规则：歌名去掉括号备注后必须正好是点的那首，剩下的字必须是歌手，比如“晴天 周杰伦”只认周杰伦唱的《晴天》；
  歌名带“原唱 / 翻自”的别人翻唱不要；拿不到完整音频（版权、只有试听）的跳过。网易云没有就自动走 B 站。
- 风险：非官方接口，网易云用户协议不允许，调用多了可能触发风控限制账号；VIP 下载的歌按会员协议只限自己听；
  网易云更新后接口可能失效，需要升级 `ncm-api` 里的版本。
- 接口会按 URL 缓存 2 分钟，所以调用时时间戳放在 URL 上（`server.py` 的 `ncm_call`）。

### 防破音

RMVPE 偶尔把某几十毫秒的音高认错一个八度（听起来就是一下破音），或者音符中间断一两帧（变嘶哑）。
服务在 RVC 合成前会修一遍音高：和前后 0.15 秒比差 9 个半音以上的帧按整八度拉回，≤40ms 的断档补上
（`f0_cleanup`、`f0_fill_gap_frames`）。实测每 40 秒拉回 3~12 处。说话变声也走这一步。

### 常调的参数（`cover/config.json`，改完重启服务）

- `clip_seconds` 唱多长；`max_song_seconds` 整首歌最长多少秒
- `f0_up_key` 升降调：`"auto"` 按 `target_f0_hz` 自动选 0 或 ±12，也可以写死数字；说话升降调是 `speech_f0_up_key`（默认 0）
- `index_rate`、`protect` 是 RVC 的音色参数
- `vocal_gain_db` 人声音量、`accomp_gain_db` 伴奏音量（默认人声 +3、伴奏 −7，人声比原曲突出约 9dB）
- `loudness_lufs` 整体响度，最后统一拉平并限幅，成品约 -13 LUFS、峰值 -2dB

### 环境备注

- Python 3.10，PyTorch 用 Apple GPU（MPS），MPS 没实现的算子自动退回 CPU。
- macOS 27 上 SciPy 1.15 加载不了，固定在 1.14.1；pyworld 需要 `setuptools<81`。

## 注意

- **Mac 睡眠 / 关机 = 她下线。** 想一直在线，就让 Mac 保持唤醒，或者照 `deploy/README.md` 搬到云服务器。
- **这个号不要在别的电脑上登电脑版 QQ**，会和 NapCat 互踢。手机 QQ 同时在线没问题。
- 挂机器人的号有被风控的可能。挂在主号上，真被风控影响的就是主号；原设计是挂小号。
- 想加看图、听语音、长期记忆，照 `docs/导入指南.md` 继续。视频识别需要额外的 Python 包，到时改用 `deploy/Dockerfile` 构建镜像。
