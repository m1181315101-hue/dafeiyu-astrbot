# 大肥鱼工具箱

大肥鱼自己写的 8 个小插件合成的一个插件，外加从 [AstrNa](https://github.com/Sisyphbaous-DT-Project/astrbot_plugin_AstrNa) 原样搬来的 3 个可选功能。
每个功能都在 AstrBot 面板 → 插件 → 大肥鱼工具箱 → 配置 里单独开关；保存后插件自动重载，不用重启 AstrBot。

| 配置里的一节 | 功能 | 原来的插件 | 默认 |
| --- | --- | --- | --- |
| private_only | 群消息不回，列出的群除外 | astrbot_plugin_private_only 1.1.0 | 开 |
| group_brevity | 群里叫她的这句只有几个字时，提醒她一条消息接住，别拆成好几条 | 新写（v1.4.0） | 开 |
| habit_check | 每天数一遍她最近的回复，挑出最突出的小毛病（群里回太长、老用同一个开头、口头禅、括号动作）写成提醒 | 新写（v1.4.0） | 开 |
| image_repeat | 群里连着几个人发同一张图（多半是表情包）时，她也跟一张；陪伴插件的复读机只认文字 | 新写（v1.5.0） | 开 |
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

## 照片

照片默认还放在 `data/plugin_data/astrbot_plugin_selfie/photos/`（AstrBot 数据目录下），对照表 `photos.json` 的写法见 `data/photos.example.json` 和 `modules/album.py` 开头的说明。
