"""从 AstrNa 原样搬来的几个模块（MIT 许可，原文见同目录 LICENSE）。

来源：https://github.com/Sisyphbaous-DT-Project/astrbot_plugin_AstrNa
版本：1.7.3（提交 8b6ba95），对准 AstrBot 4.29.3。
只搬了下面这些文件，内容一字未改：
- utils/patching.py、utils/event_stop.py
- modules/tool_call_preamble.py（隐藏工具调用前的过场白）
- modules/tool_history_context.py（工具调用历史压缩）
- modules/output_length_limiter.py（输出字数限制；过场白模块也要用它的两个小函数）
- modules/image_history_context.py（工具历史压缩要用它的函数）
要升级就从上游整份覆盖这几个文件，别在这里改。
"""
