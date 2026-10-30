# 大肥鱼工具箱

让 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 机器人在群里更像个群友的一组小功能。主要按微信适配（配合 [astrbot-mac-wechat-connector](https://github.com/m1181315101-hue/astrbot-mac-wechat-connector)），QQ（NapCat）也能用。

- **图片复读**：群里连着三条是同一张图，就跟一张。在微信上发成会动、按表情大小显示的表情，不是一张大图。
- **分清在跟谁说**：有人引用机器人的话、却 @ 了别人时，提醒它这句主要是说给谁听的，别答非所问。
- **群里回短点**：叫它的这句只有几个字时，提醒它一条消息接住，别拆成好几条、别铺垫。
- **说话习惯自检**：每天数一遍它最近的回复，挑出最突出的小毛病（回太长、老用同一个开头、口头禅），写成提醒放进之后每一轮。不额外调模型。

另外还有表情转换、拍一拍、新人欢迎、平台提示，以及发照片、唱歌、发语音几个工具。每个功能都在 AstrBot 面板 → 插件 → 大肥鱼工具箱 → 配置 里单独开关，保存后插件自动重载，不用重启 AstrBot。

## 安装

- 在 AstrBot 面板的插件页用仓库地址 `https://github.com/m1181315101-hue/astrbot_plugin_dafeiyu` 安装；或者把整个目录放进 `data/plugins/astrbot_plugin_dafeiyu/`，重启 AstrBot。
- 要求 AstrBot 4.24.1 起（按 4.29.3 测过），更早的版本会拒绝加载。
- 想让机器人只在几个群里说话：打开「只回私聊」（`private_only`，默认关），在里面列出放行的群。

它原来是「大肥鱼」（DeepSeek 吉祥物人设的 QQ / 微信聊天机器人）自己用的 8 个小插件，合成了一个，再加上从 [AstrNa](https://github.com/Sisyphbaous-DT-Project/astrbot_plugin_AstrNa) 原样搬来的 3 个可选功能（默认关）。人设相关的东西（拍一拍、新人欢迎的提示词，表情名单、同事名字）是按大肥鱼写的，别的角色用可以在配置里改提示词。

## 微信上专门处理过的地方

配合微信连接器（把微信接成 OneBot v11）用得最多、测得最全：

- 表情转换把 `[流泪]` 这类 QQ 表情名换成微信认的表情名。
- 拍一拍默认只回微信。
- 新人欢迎认连接器转出的入群通知。
- 「引用她又 @ 别人」要连接器 0.13.0 起转出 @ 段才认得出。
- 图片复读在微信上把静态图转成单帧 GIF，配合连接器 0.14.0 发成表情。

QQ（NapCat）上大部分功能一样能用，只是上面这几处是照着微信调的。

## 依赖和外部服务

依赖都在 AstrBot 自带的环境里（Pillow、aiohttp）。有几个功能要外部服务，不配就自动关着或退回：

- 唱歌要翻唱服务（`sing.service_url`）。
- 语音条变声要变声服务（`voice.rvc_url`）。
- 语音转写和视频理解要借一个填了百炼 key 的 AstrBot 提供商（`face.dashscope_key_providers`）。

## 功能一览

| 配置里的一节 | 功能 | 原来的插件 | 默认 |
| --- | --- | --- | --- |
| private_only | 群消息不回，列出的群除外 | astrbot_plugin_private_only 1.1.0 | 关 |
| group_brevity | 群里叫她的这句只有几个字时，提醒她一条消息接住，别拆成好几条 | 新写（v1.4.0） | 开 |
| habit_check | 每天数一遍她最近的回复，挑出最突出的小毛病（群里回太长、老用同一个开头、口头禅、括号动作）写成提醒 | 新写（v1.4.0） | 开 |
| image_repeat | 群里连着三条都是同一张图（多半是表情包，同一个人连发也算）时，她也跟一张；陪伴插件的复读机只认文字 | 新写（v1.5.0） | 开 |
| reply_direction | 群里有人引用她的话、同时 @ 了别人时，告诉她这句在跟谁说，让她读懂再接 | 新写（v1.2.0） | 开 |
| platform_hint | 系统提示词末尾标明消息来自 QQ 还是微信 | astrbot_plugin_platform_hint 1.0.0 | 开 |
| face | 文字表情转真表情、收到的表情/语音/视频翻成文字、群聊身份标记、发送前擦草稿 | astrbot_plugin_face_convert 1.3.1 | 开 |
| pat | 拍一拍 / 戳一戳时用她的口吻回一句 | astrbot_plugin_pat 1.0.0 | 开 |
| welcome | 新人进群时欢迎一句并 @ 新人 | astrbot_plugin_welcome 1.0.0 | 开 |
| selfie | `send_selfie` 工具：从相册挑照片发 | astrbot_plugin_selfie 1.1.0 | 开 |
| sing | `sing_song` 工具：调翻唱服务唱一段 | astrbot_plugin_sing 1.0.0 | 开 |
| voice | `tts_speak` 工具，和「语音开 / 语音关 / 语音状态」指令 | astrbot_plugin_voice 1.0.0（指令原在 face_convert） | 开 |
| hide_tool_preamble | 隐藏调工具前的过场白 | AstrNa 1.7.3 | 关 |
| tool_history | 压缩历史里的大段工具结果 | AstrNa 1.7.3 | 关 |
| output_limit | 回复超长时用小模型改短 | AstrNa 1.7.3 | 关 |

## 目录

- `main.py`：按开关建模块、把 AstrBot 的钩子接给模块；某个模块建不起来只关它自己。
- `modules/`：我们自己的功能，一个功能一个文件，从原插件原样搬来，只改了读配置的地方（每个文件开头写了改了什么）。
- `astrna/`：从 AstrNa 搬来的文件，一字未改，许可证见 `astrna/LICENSE`（MIT）；升级就从上游整份覆盖。
- `data/`：表情字典（`face_map.json`、`wx_emoji.json`）和相册对照表示例 `photos.example.json`。
- `tests/`：`python -m pytest tests`（要在装了 AstrBot 的环境里跑）。

## 协议

MIT，见 `LICENSE`。`astrna/` 下的文件来自 [AstrNa](https://github.com/Sisyphbaous-DT-Project/astrbot_plugin_AstrNa)，保留它自己的 MIT 协议（`astrna/LICENSE`）。

## 照片

照片默认还放在 `data/plugin_data/astrbot_plugin_selfie/photos/`（AstrBot 数据目录下），对照表 `photos.json` 的写法见 `data/photos.example.json` 和 `modules/album.py` 开头的说明。
