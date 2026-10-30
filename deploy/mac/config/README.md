# 本机版用到的插件和配置（复刻用）

这里记的是 Mac 本机版实际在跑的插件清单，以及和默认值不同的配置项。第三方插件**不复制代码**，只记来源和版本，去它们的仓库装（AstrBot 面板 → 插件 → 从仓库链接安装）。

记录时间：2026-10-28（下午更新），AstrBot 4.29.3（镜像钉的是 `soulter/astrbot:v4.29.0`，面板里在线升到了 4.29.3；容器重建会回到镜像版本）。

## 插件清单

| 插件 | 版本 | 来源 | 状态 | 用途 |
|---|---|---|---|---|
| `astrbot_plugin_dafeiyu`（大肥鱼工具箱） | v1.5.5 | 本仓库 `plugin/`（单独开源在 [astrbot_plugin_dafeiyu](https://github.com/m1181315101-hue/astrbot_plugin_dafeiyu)，MIT） | 启用 | 2026-10-30 由下面 8 个自写插件合成，每个功能在插件配置里单独开关：只回私聊、引用她又 @ 别人时说明在跟谁说（v1.2.0 起）、群里回短点和每日说话习惯自检（v1.4.0 起）、图片复读（v1.5.0 起）、平台提示、表情转换与收信翻译、拍一拍、新人欢迎、`send_selfie`、`sing_song`、`tts_speak`；另带从 AstrNa 搬来的过场白隐藏、工具历史压缩、输出字数限制，2026-10-30 下午起开着：过场白群聊私聊都隐藏；工具历史压缩开；字数限制 300 字、清洗模型 `deepseek/deepseek-flash`、主人的两个私聊不限 |
| `astrbot_plugin_face_convert` 等 8 个 | — | 本仓库 `plugin/`（已删） | **已合并** | face_convert、private_only、voice、sing、selfie、platform_hint、welcome、pat，合进上面的工具箱，旧目录不再用 |
| `astrbot_plugin_group_followup` | v1.0.0 | 本仓库 `plugin/` | **停用** | 群聊续聊，现在交给陪伴插件 |
| `astrbot_plugin_private_companion`（陪伴面板） | 6.5.6 | [menglimi/astrbot_plugin_private_companion](https://github.com/menglimi/astrbot_plugin_private_companion)（仓库未声明许可证） | 启用 | 生活日程、关系、主动消息、群聊续聊与读空气、TTS 增强 |
| `meme_manager`（表情包） | 5.2.10 | [anka-afk/astrbot_plugin_meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager)（MIT） | 启用 | 表情包图片；改了两处：打开「表情使用频率」提示（`generation.prompt.quantity_guidance_enabled = true`，用它默认的「每约 4 条回复配 1 张图」）；2026-10-30 起开了自动收录（偷群里的表情包），见下面「偷表情包」 |
| `astrbot_plugin_livingmemory` | 2.8.0 | [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory)（AGPL-3.0） | **已卸载** | 长期记忆；要 Embedding 提供商，没配一直初始化失败，换成了下面的 `memory_companion` |
| `astrbot_plugin_memory_companion`（我会牢牢记住你） | 1.10.5 | [menglimi/astrbot_plugin_memory_companion](https://github.com/menglimi/astrbot_plugin_memory_companion)（仓库未声明许可证） | 启用 | 长期记忆，陪伴插件作者的配套插件；2026-10-30 起开了向量检索和重排（阿里云百炼），其余默认 |
| `astrbot_plugin_proactive_chat` | v1.2.6 | [Pancakes-Labs/astrbot_plugin_proactive_chat](https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat)（AGPL-3.0） | **已卸载** | 主动消息；和陪伴插件重复 |
| `astrbot_plugin_dynamic_life_state` | v0.3.1 | [Hola-Gracias/astrbot_plugin_dynamic_life_state](https://github.com/Hola-Gracias/astrbot_plugin_dynamic_life_state)（AGPL-3.0） | **已卸载** | 生活时间线；和陪伴插件的日程重复，两份作息会打架 |

停用 = 装着但在面板「插件」里关掉，没删；已卸载 = 在面板里删掉了，只留记录。

表情包插件装了三个包：「官方表情包1号 · 社区语义增强版」（`ddzs987-semantic-001`）、「Clover Days 表情包 · 鹰仓杏铃」（`clover-days-meme-pack`）、「永雏塔菲表情包」（`yctf-taffy`），都在插件的资源广场里装。默认选包规则现在只选了「永雏塔菲」（选包规则存在插件数据目录的 `selection_rules.json`，不在配置里）。

## 配置

占位符：`<填你自己的>` 是密钥或口令，`<主人小号QQ>` 是主人用来找她的另一个号，`<允许的群号>` 是 `private_only` 和陪伴插件都放行的那个 QQ 群，`<微信群的 OneBot 号>` 是微信连接器给放行的微信群算出的整数号（`bridge.py lookup` 能查到），也要一起加进 `private_only` 的白名单。

- [`cmd_config.changes.json`](cmd_config.changes.json)：AstrBot 主配置（`data/cmd_config.json`）里和默认值不同的项，按原结构写，面板里逐项改或者合并进去都行。面板账号密码没导出。
  `provider_tts_settings.enable=false` 和默认值相同，但很关键（不让 AstrBot 按概率把回复变语音），所以也写上了。
  `platform` 里的 `wechat` 是微信连接器用的第二个 OneBot v11 平台（反向 WS 端口 6200），见 [`wechat-connector/README.md`](../../../wechat-connector/README.md)。
- [`astrbot_plugin_private_companion.changes.json`](astrbot_plugin_private_companion.changes.json)：陪伴插件里改过的项，键名是「分组.配置项」，在陪伴面板或插件配置页里找同名项改。
  - 没导出的：插件根据人格自动起草的三段提示词（`life_schedule_config` 里的日程人设、世界观、用户与关系）。导入人格后让插件重新起草，再检查里面和主人身份有关的句子：起草时如果用的是旧人格，会写成「和她说话的都不是主人」，要改成按 `<主人小号QQ>` 认主人。接了微信的话还要补上微信：活动场景写「QQ 和微信」，微信上按 `<主人微信ID>`（连接器给主人微信的 OneBot 号）认主人。
  - 人格 2026-10-28 重写成 v3 后，本机版手动对齐了这三段：日程人设的「职业/身份」写成「主人养的鲸鱼娘、不是客服也不是助手」，「性格」「爱好」换成 v3 的态度和喜好，加了「厌恶」，「其他补充」加上动作只在得意开心时写；世界观去掉写给程序的那句；用户关系把「默认不追问、陈述句结尾」改成「可以接梗、反问、调侃」。认主人、微信号、主人吩咐照做这些照旧。
  - `target_user_ids`（主用户）填 `<主人小号QQ>`，要和人格里的 `{主人小号QQ}` 是同一个号；接了微信再加上 `<主人微信ID>`。只写在人格里不够：不在这个名单里的人，陪伴插件会在提示里标「该 ID 不是主要用户」（私聊里还会叮嘱别把人格里的主人套到对方身上），比人格更具体，她就不认了。
  - 群聊：主动插话打开（每群每天最多 6 次、间隔至少 60 分钟），强唤醒词「大肥鱼、肥鱼、大飞鱼」，兴趣唤醒 30%，回完后不用 @ 最多再接 3 轮。
  - 复读机：同一句话 2 分钟内连着出现 3 次时，跟读 50%、打断（发「禁止复读」）5%（默认 18% 和 10%）；没出手的话下一次复读两边各加 12%，中间插进别的话就重新计数，次数和主动插话共用每天 6 次。默认值下作者本机一个微信群一天里有 4 次复读，她出手 2 次都是打断，看着像没触发。
  - 读空气防互刷放宽到 120 秒内 6 条（默认 180 秒内 3 条）：默认值下她在群里回过两条，别人再喊「肥鱼」就要先过一个小模型判断（不看人格），常被判成沉默；回满三条后一律不回。
  - 回得快一点：群里热闹时的合并等待 8→3 秒（`group_high_intensity_merge_seconds`）、只喊一两个字时等补话 15→6 秒（`group_wakeup_short_text_wait_seconds`）、只发图片或表情包时等补话 8→4 秒（`image_message_debounce_seconds`）。按日志拆过：微信上从收到消息到发出回复中位约 7 秒，大头是这几种等待，不是连接器。代价是热闹时合并得少、可能多回几条。
  - 偷表情包（2026-10-30，`meme_manager` 的自动收录）：群里大家爱发的表情包收进她的表情包库，从哪个群偷的只在哪个群里用。
    - 每个允许回复的群建一个本地包 `stolen-<群号>`（名字「群里偷的表情包·群名」），分类和她原来用的包对齐（happy、sad、angry、confused、teasing、affection、shy、sleep、food、work、money、greeting），按情绪挑图时会一起算进去。
    - `selection_rules.json` 给每个群加两条会话规则：目标写群号一条、写 `平台:GroupMessage:群号` 一条（插件收图时用的会话 ID 是群号，往提示里放分类时用的是后者），包顺序 `[stolen-<群号>, 原来的三个默认包]`。自动收录不指定目标包，就收进当前会话的第一个包，也就是这个群的偷图包；发图时从这几个包同一分类的图里随机挑，偷来的混在里面，用得少。私聊和其他群照旧只用默认包。
    - 自动收录 `auto_collect`：`enabled` 开；看图模型 `aliyun/qwen3.8-flash`；`manual_review` 关（直接入包，分类拿不准的进待审核、不会被发出去）；`content_review_enabled` 开，提示词末尾加了一句「也拒绝收录：看起来是某个人自己的自拍或生活照（不是网上流传的表情包）、聊天记录截图、带二维码或联系方式的图片」；`scope` 只列这几个群（`group:群号`）；平台标了是表情的图（QQ）抽样 30%；每天最多识别 40 次。微信连接器给的表情包没有平台标记，插件当普通图片处理：第一次见只记下，第二次 45% 概率去识别，第八次一定识别（按图片内容的 sha256 数，每个包分开数），所以越多人发的越容易被偷。
    - 收错了在表情包插件的网页面板里按包删。这些包和规则存在插件数据里，不在配置里，换机要重建。
  - 说话风格（2026-10-30）：默认语气 `basic_config.default_style` 从「温柔」改成「嘴硬俏皮」，跟人格对齐；已有的 26 个用户身上的「温柔」也一起改了（这个存在插件数据 `companions.json` 的 `users.*.style` 里，不在配置里，导出看不到，换机要在陪伴面板里改）。群聊表达学习 `memory_habit_config.expression_group_learning_source_mode` 从 `disabled` 改成 `all`：插件会把群里脱敏后的短说法、梗模板学下来，按场景用到她的回复里，发送前的表达审核（`enable_expression_style_review`）照旧开着。原来只从主人私聊学，攒了 33 条样本、一条规则都没学出来。
  - QQ 群引用框（2026-10-30）：`timer_config.quote_skip_short_reply_chars` 0→30，30 字以内的短回复不带引用框。插件开着「回复时引用触发消息」，原来 QQ 群里近一半回复都带引用框，短短一句也带，很像机器人；微信发不了引用，不受影响。
  - 私聊连发合并（2026-10-30）：`message_debounce_config.text_message_debounce_seconds` 0→5 秒。有人习惯一句话拆成几条连着发，原来每条都单独回（作者本机微信私聊两天里 29 次连发、16 次分两轮以上回）；连发间隔中位 3 秒、75% 在 5 秒内、九成在 10 秒内。改成每条私聊等 5 秒，5 秒内又来一条就接着等（最长 12 秒、最多合 8 条），合成一轮回；她回复途中又来的补话，插件会把没发出的那条作废，连同补话重新回。代价是私聊每条回复晚 5 秒左右。这个等待对群聊也有一点影响：同一个人在群里叫她以后、她回复途中又补的话，也会这样合进去。
  - 群聊高强度收口（`enable_group_high_intensity_mode`）关掉了：开着时一分钟内被叫 3 次就把后面的合并成一轮处理，实测有写好的回复没发出去、合并缓冲里的消息也没再出来。关掉后每个叫她的人单独处理，热闹时回得多一些。
  - 陪伴插件的 TTS 增强（`voice_action_config.enable_tts_enhancement`）关掉了：它每轮按 25% 的概率接管语音，接管那一轮会把回复类型从「模型生成」改成「普通结果」（防止 AstrBot 自带 TTS 再处理一遍），可 AstrBot 的分段回复只对「模型生成」的回复生效，于是约三成回复几行字挤成一条发。它用的还是 edge_tts（晓伊）的声音，一天只真发出过 6 条语音；要语音时走本仓库的 `tts_speak`（NORA 的声音），不受影响。
  - 主动私聊的「连发」（`private_followup_config.enable_proactive_burst`）2026-10-30 关掉了：开着时一次主动会连着发两条（间隔 45–180 秒），实测有人 4 分钟里收到两条。在陪伴面板里手动打开了「允许主动私聊」的朋友，每天主动上限从 3 改成 1（这一项存在插件数据 `companions.json` 里，不在配置里，导出看不到）。
  - 陪伴插件自带的被动戳一戳（`reactive_poke_config.enable_reactive_poke`）保持关闭（默认值）：它生成回复时不带人格（系统提示只有一句「你是一位正在陪伴用户的 AI 角色」），还有 30% 的概率直接回「哎呀，被发现了~」这类预设句；反戳走的是 QQ 的接口，微信上不对。拍一拍 / 戳一戳交给本仓库大肥鱼工具箱的「拍一拍」（`pat`）。
  - `basic_config.enable_proactive_only_mode`（仅保留主动能力）要**保持关闭**（默认值，所以导出里没有它）：开着的话群聊的复读、唤醒、续接、插话和私聊里的语音都会停掉。
  - `experimental_motivation_config.enable_reaction_expression_experiment`（表情表达实验）关着（默认值，所以导出里没有它）。
  - 陪伴插件自带的 `pc_find_reaction_image`（找反应图）工具要在 AstrBot 面板「函数工具」里**停用**（存在全局偏好 `inactivated_llm_tools` 里）。它用的是陪伴插件自己的素材库，没往里导图时是空的；可它的说明会鼓励模型「素材库可能是空的也可以试试」，于是有人要表情包时，她大多去调这个工具，拿到「素材库为空」，图就没了，表情包插件根本轮不到。以后往陪伴插件的素材库导了图再打开。
  - 2026-10-30 为了给提示词减负，又在「函数工具」里停了 12 个（同样存在 `inactivated_llm_tools`）：每次请求都会带上全部工具的说明，量下来工具说明占了一次聊天请求的一半多，人格只占 8%。停的是 3 天里一次都没成功用过的：陪伴插件的 QQ 空间三个（`pc_qzone_view_feed`、`pc_qzone_publish_feed`、`pc_qzone_reply_my_comment`）、生图 `pc_generate_photo`（唯一一次调用报错，生图后端没接上）、备忘录 `pc_manage_memo`（记忆插件的笔记能代替）、批量发送 `pc_send_to_groups` / `pc_send_to_private_users`、预约群转发 `pc_schedule_group_relay`、看自己作品 `pc_view_creative_work`；还有 anysearch 插件自带的三个搜索工具（`anysearch_search`、`anysearch_batch_search`、`anysearch_extract`），和 AstrBot 自带的网页搜索 `web_search_anysearch` 是同一个后端，留自带的那个。以后要用哪个，在面板里重新打开就行。
  - 同一天还关了 AstrBot 的 4 个内置技能（`data/skills.json` 里 documents、pdf、skill-creator、spreadsheets 的 `active` 改成 `false`）：它们要沙箱才能跑，本机 `computer_use_runtime` 是 `none`，用不了，可每次请求都带着约 3500 字说明。
  - MCP 工具（比如藏宝阁那 15 个）用这个办法停不掉：AstrBot 每次连上 MCP 服务都重新注册一遍，忘掉停用状态（`my_holdings` 一直在停用清单里，可每次请求照样带着）。要藏得在 MCP 服务那边处理。
  - `photo_action_config` 里把她的自拍设成人格参考图（`photo_reference_library` 一行是「图片路径 || 外观说明」），以后接上生图后端时用来保持长相。图片本身不在仓库里，换成你自己的。
- 其他第三方插件（表情包、`memory_companion`）的配置都是默认值（表情包另开了「表情使用频率」提示，见上表），只有下面这一处例外。
- `memory_companion` 的向量检索（2026-10-30）：原来只按关键词找记忆，平均每次回复有 20 多条候选因为「关键词命中太弱」被挡掉（比如聊「吃火锅」找不到写成「去海底捞」的那条）。在 AstrBot「服务提供商」里加了阿里云百炼的 Embedding（`dashscope_embedding`，`qwen3.7-text-embedding-flash`，1024 维）和 Rerank（`bailian_rerank`，`qwen3.7-text-rerank`），插件配置里 `retrieval.embedding_enabled` 打开，`retrieval.embedding_provider_id`、`retrieval.rerank_provider_id` 填这两个 ID，其余检索参数默认（相似度门槛 0.34：这个模型下不相关的两句也有 0.39 左右，靠重排把不相关的筛掉）。存量记忆由插件后台每 5 分钟补 50 条向量。密钥只在本机 AstrBot 里。
- 看图（2026-10-30）：陪伴插件看图（私聊单图、群聊图片、引用和合并消息里的图）原来用聊天的 `deepseek/deepseek-flash`。它要先思考 500–900 字，看引用图时插件只给 260 token 上限，常常思考完就没额度写答案、返回空；群图有时思考超过 12 秒超时。在「服务提供商」里加了阿里云百炼的 `aliyun/qwen3.8-flash`（OpenAI 兼容，能力勾图片），给它 `custom_extra_body` 加 `enable_thinking: false`（关思考后每张 1.6–2.5 秒、约 50 token，测试表情包四张全看懂），陪伴插件 `model_assignment_config.PLUGIN_VISION_PROVIDER_ID` 改成它，`model_fallback_overrides` 里把看图兜底设成 `deepseek/deepseek-flash`。
- 语音和视频（2026-10-30）：大肥鱼工具箱的 `face` 一节，语音转写（`qwen3-asr-flash`）和视频理解（`qwen3-vl-plus`）要百炼 key，原来只从 `dashscope_tts` 提供商拿，这个提供商删了以后收到的语音、视频一直识别不了。工具箱 v1.1.0 起按 `face.dashscope_key_providers` 的顺序借 key，现在借的是 `dashscope_embedding`。微信连接器本来就不转语音和视频，这两样只对 QQ 有用。
- **`memory_companion` 有一处本地改动（2026-10-29，插件升级会被覆盖，升级后要重新改）**：`core/summarizer.py` 的 `summary_quality` 里，总结只要出现「某用户、某人、有人、群成员」这类词就判成低质量、进不了长期记忆；但它按字面找「有人」，「没有人」「所有人」也会被拦。微信群两天里 134 次被拒全是这条，约三分之一（46 条）是这么误判的。改法：查这些词之前，先把「没有人」「所有人」「只有人」「有人气」从总结里去掉再查，其余规则不动。这个问题还没提给作者。
- **`private_companion` 有一处本地改动（2026-10-30，插件升级会被覆盖，升级后要重新改）**：`main.py` 的 `_review_group_question_wakeup_reply_before_send`（答疑唤醒的回复发送前「碰瓷」复核）判断标准末尾加了三行：待发送回复只是一句很短的接梗、吐槽或玩笑（20 字以内、不解释、不追问）可以发；只是简短地请教群里的黑话、梗、缩写是什么意思也可以发；这两条不适用于触发句明确 @ 了别人、或只是两个人之间来回说的话。原来两天 26 次答疑唤醒被拦 23 次，看复核理由大多拦得对（触发句是「谁懂」「这合理吗」这类接话吐槽），但也拦掉了她顺口请教「猛攻是什么」这种。这段文件里换行符 CRLF 和 LF 混用，补的时候按原样保留，别整份转换。插件 6.5.6。
- **AstrBot 在跑的时候，别在 macOS 本机直接打开 `data/` 下的 SQLite 库**（`data_v4.db`、插件的 `.db`），只读也不行：这些库是 WAL 模式，锁和共享内存跨不过 Docker Desktop 的虚拟机，本机一关库就可能把容器正在写的 WAL 截掉。2026-10-30 这样坏过一次 `data_v4.db` 的定时任务表。要看就 `docker cp` 一份出来看拷贝，要改就先停 AstrBot。
- 大肥鱼工具箱：配置在面板 → 插件 → 大肥鱼工具箱 → 配置里改（存在 `data/config/astrbot_plugin_dafeiyu_config.json`），保存后插件自动重载。要填的有：只回私聊的群、欢迎的群、拍一拍的平台、主人和女主人的号、翻唱服务和变声服务的地址与口令（和 `cover/config.json` 的 `token` 一样）。照片放进 `data/plugin_data/astrbot_plugin_selfie/photos/`（沿用原来的文件夹）。
- 其余还在 `plugin/` 里的自写插件（`group_followup` 等）：插件目录下的 `config.example.json` 复制成 `config.json`。

## 人格

`persona/大肥鱼-人格-本机版.md`，导入前把正文里的占位符（`{主人}`、`{主人别名}`、`{主人小号QQ}`、微信和女主人的几个号）换成自己的，清单见文件开头。
