# 本机版用到的插件和配置（复刻用）

这里记的是 Mac 本机版实际在跑的插件清单，以及和默认值不同的配置项。第三方插件**不复制代码**，只记来源和版本，去它们的仓库装（AstrBot 面板 → 插件 → 从仓库链接安装）。

记录时间：2026-10-28（下午更新），AstrBot 4.29.3（镜像钉的是 `soulter/astrbot:v4.29.0`，面板里在线升到了 4.29.3；容器重建会回到镜像版本）。

## 插件清单

| 插件 | 版本 | 来源 | 状态 | 用途 |
|---|---|---|---|---|
| `astrbot_plugin_face_convert` | v1.2.1 | 本仓库 `plugin/` | 启用 | `[旺柴]` 这类写法变成真 QQ 表情 |
| `astrbot_plugin_private_only` | v1.1.0 | 本仓库 `plugin/` | 启用 | 私聊都回，群里只回指定的群 |
| `astrbot_plugin_voice` | v1.0.0 | 本仓库 `plugin/` | 启用 | `tts_speak`：有人要语音才发，edge-tts + RVC |
| `astrbot_plugin_sing` | v1.0.0 | 本仓库 `plugin/` | 启用 | `sing_song`：调本机翻唱服务 |
| `astrbot_plugin_selfie` | v1.0.0 | 本仓库 `plugin/` | 启用 | `send_selfie`：有人要自拍就从照片文件夹挑一张原样发 |
| `astrbot_plugin_platform_hint` | v1.0.0 | 本仓库 `plugin/` | 启用 | 系统提示末尾标【当前平台】：QQ 还是微信 |
| `astrbot_plugin_group_followup` | v1.0.0 | 本仓库 `plugin/` | **停用** | 群聊续聊，现在交给陪伴插件 |
| `astrbot_plugin_private_companion`（陪伴面板） | 6.5.6 | [menglimi/astrbot_plugin_private_companion](https://github.com/menglimi/astrbot_plugin_private_companion)（仓库未声明许可证） | 启用 | 生活日程、关系、主动消息、群聊续聊与读空气、TTS 增强 |
| `meme_manager`（表情包） | 5.2.9 | [anka-afk/astrbot_plugin_meme_manager](https://github.com/anka-afk/astrbot_plugin_meme_manager)（MIT） | 启用 | 表情包图片，配置全默认 |
| `astrbot_plugin_livingmemory` | 2.8.0 | [lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory)（AGPL-3.0） | **已卸载** | 长期记忆；要 Embedding 提供商，没配一直初始化失败，换成了下面的 `memory_companion` |
| `astrbot_plugin_memory_companion`（我会牢牢记住你） | 1.10.5 | [menglimi/astrbot_plugin_memory_companion](https://github.com/menglimi/astrbot_plugin_memory_companion)（仓库未声明许可证） | 启用 | 长期记忆，陪伴插件作者的配套插件；Embedding 可选，配置全默认 |
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
  - 群聊高强度收口（`enable_group_high_intensity_mode`）关掉了：开着时一分钟内被叫 3 次就把后面的合并成一轮处理，实测有写好的回复没发出去、合并缓冲里的消息也没再出来。关掉后每个叫她的人单独处理，热闹时回得多一些。
  - 陪伴插件的 TTS 增强（`voice_action_config.enable_tts_enhancement`）关掉了：它每轮按 25% 的概率接管语音，接管那一轮会把回复类型从「模型生成」改成「普通结果」（防止 AstrBot 自带 TTS 再处理一遍），可 AstrBot 的分段回复只对「模型生成」的回复生效，于是约三成回复几行字挤成一条发。它用的还是 edge_tts（晓伊）的声音，一天只真发出过 6 条语音；要语音时走本仓库的 `tts_speak`（NORA 的声音），不受影响。
  - `basic_config.enable_proactive_only_mode`（仅保留主动能力）要**保持关闭**（默认值，所以导出里没有它）：开着的话群聊的复读、唤醒、续接、插话和私聊里的语音都会停掉。
  - `experimental_motivation_config.enable_reaction_expression_experiment`（表情表达实验）关着（默认值，所以导出里没有它）。
  - 陪伴插件自带的 `pc_find_reaction_image`（找反应图）工具要在 AstrBot 面板「函数工具」里**停用**（存在全局偏好 `inactivated_llm_tools` 里）。它用的是陪伴插件自己的素材库，没往里导图时是空的；可它的说明会鼓励模型「素材库可能是空的也可以试试」，于是有人要表情包时，她大多去调这个工具，拿到「素材库为空」，图就没了，表情包插件根本轮不到。以后往陪伴插件的素材库导了图再打开。
  - `photo_action_config` 里把她的自拍设成人格参考图（`photo_reference_library` 一行是「图片路径 || 外观说明」），以后接上生图后端时用来保持长相。图片本身不在仓库里，换成你自己的。
- 其他第三方插件（表情包、`memory_companion`）的配置都是默认值。
- 本仓库自己的插件：各插件目录下的 `config.example.json` 复制成 `config.json`。`astrbot_plugin_selfie` 的照片放进 `data/plugin_data/astrbot_plugin_selfie/photos/`。

## 人格

`persona/大肥鱼-人格-本机版.md`，导入前替换 `{主人}`、`{主人别名}`、`{主人小号QQ}`。
