import sys
import os

from typing import (
    Literal
)

MAX_TIMEOUT: Literal[600] = 600

NODE_GLOBAL_KEY: Literal["_node_global"] = "_node_global"
BOT_GLOBAL_KEY: Literal["_bot_global"] = "_bot_global"

# used by Matcher
RECEIVE_KEY: Literal["_receive_{id}"] = "_receive_{id}"
"""`receive` 存储 key"""
LAST_RECEIVE_KEY: Literal["_last_receive"] = "_last_receive"
"""`last_receive` 存储 key"""
ARG_KEY: Literal["{key}"] = "{key}"
"""`arg` 存储 key"""
REJECT_TARGET: Literal["_current_target"] = "_current_target"
"""当前 `reject` 目标存储 key"""
REJECT_CACHE_TARGET: Literal["_next_target"] = "_next_target"
"""下一个 `reject` 目标存储 key"""
PAUSE_PROMPT_RESULT_KEY: Literal["_pause_result"] = "_pause_result"
"""`pause` prompt 发送结果存储 key"""
REJECT_PROMPT_RESULT_KEY: Literal["_reject_{key}_result"] = "_reject_{key}_result"
"""`reject` prompt 发送结果存储 key"""

# used by Rule
REGEX_MATCHED: Literal["_matched"] = "_matched"
"""正则匹配结果存储 key"""
STARTSWITH_KEY: Literal["_startswith"] = "_startswith"
"""响应触发前缀 key"""
ENDSWITH_KEY: Literal["_endswith"] = "_endswith"
"""响应触发后缀 key"""
FULLMATCH_KEY: Literal["_fullmatch"] = "_fullmatch"
"""响应触发完整消息 key"""
KEYWORD_KEY: Literal["_keyword"] = "_keyword"
"""响应触发关键字 key"""
COUNTER_INFO: Literal["_counter"] = "_counter"
"""计数器触发信息 info"""
COUNTER_STATE: Literal["_counter_state"] = "_counter_state"
"""用于在global_state持久化储存计数器状态 state"""

PREFIX_KEY: Literal["_prefix"] = "_prefix"
"""命令前缀存储 key"""

CMD_KEY: Literal["command"] = "command"
"""命令元组存储 key"""
RAW_CMD_KEY: Literal["raw_command"] = "raw_command"
"""命令文本存储 key"""
CMD_ARG_KEY: Literal["command_arg"] = "command_arg"
"""命令参数存储 key"""
CMD_START_KEY: Literal["command_start"] = "command_start"
"""命令开头存储 key"""
CMD_WHITESPACE_KEY: Literal["command_whitespace"] = "command_whitespace"
"""命令与参数间空白符存储 key"""

SHELL_ARGS: Literal["_args"] = "_args"
"""shell 命令 parse 后参数字典存储 key"""
SHELL_ARGV: Literal["_argv"] = "_argv"
"""shell 命令原始参数列表存储 key"""

WINDOWS = sys.platform.startswith("win") or (sys.platform == "cli" and os.name == "nt")