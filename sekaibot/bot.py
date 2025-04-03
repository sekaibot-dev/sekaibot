import json
import signal
import sys
import threading
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any  # type: ignore

import anyio
import yaml
from pydantic import ValidationError, create_model  # pyright: ignore[reportUnknownVariableType]

from sekaibot.config import ConfigModel, MainConfig, NodeConfig
from sekaibot.internal.node import Node
from sekaibot.internal.node.load import NodesLoader
from sekaibot.internal.node.manager import NodeManager
from sekaibot.log import configure_logging, logger
from sekaibot.typing import BotHook, EventHook
from sekaibot.utils import (
    ModulePathFinder,
    TreeType,
    cancel_on_exit,
    flatten_tree_with_jumps,
    is_config_class,
)

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


def check_group_keywords(text: str, keywords: list) -> bool:
    """
    检查文本中是否包含任意关键字，返回 True 或 False
    """
    for kw in keywords:
        if kw in text:
            return True
    return False


def is_at_bot(event: dict) -> bool:
    """
    根据 event 判断是否 at 了 bot。
    规则：如果 event['startwith_atbot'] == True，则认为 at 了 bot
    """
    return event.get("startwith_atbot", False)


def is_private_message(event: dict) -> bool:
    """
    判断是否是私聊消息
    """
    return event.get("message_type") == "private"


class Bot:
    config: MainConfig
    manager: NodeManager
    nodes_loader: NodesLoader

    nodes_tree: TreeType[type[Node[Any, Any, Any]]]
    nodes_list: list[tuple[type[Node[Any, Any, Any]], int]]
    node_state: dict[str, Any]
    plugin_dict: dict[str, Any]
    global_state: dict[str, Any]

    _should_exit: anyio.Event
    _restart_flag: bool  # 重启标记
    _module_path_finder: ModulePathFinder  # 用于查找 nodes 的模块元路径查找器
    _raw_config_dict: dict[str, Any]  # 原始配置字典

    _config_file: str | None  # 配置文件
    _config_dict: dict[str, Any] | None  # 配置
    _handle_signals: bool  # 是否处理信号

    _extend_nodes: list[
        type[Node[Any, Any, Any]] | str | Path
    ]  # 使用 load_nodes() 方法程序化加载的节点列表
    _extend_node_dirs: list[Path]  # 使用 load_nodes_from_dirs() 方法程序化加载的节点路径列表

    # 钩子
    _bot_run_hooks: list[BotHook]
    _bot_exit_hooks: list[BotHook]
    _event_preprocessor_hooks: list[EventHook]
    _event_postprocessor_hooks: list[EventHook]

    def __init__(
        self,
        *,
        config_file: str | None = "config.toml",
        config_dict: dict[str, Any] | None = None,
        handle_signals: bool = True,
    ):
        """初始化 SekaiBot，读取配置文件，创建配置。

        Args:
            config_file: 配置文件，如不指定则使用默认的 `config.toml`。
                若指定为 `None`，则不加载配置文件。
            config_dict: 配置字典，默认为 `None。`
                若指定字典，则会忽略 `config_file` 配置，不再读取配置文件。
            _handle_signals: 是否处理结束信号，默认为 `True`。
        """
        self.config = MainConfig()
        self.manager = NodeManager(self)
        self.nodes_loader = NodesLoader(self)
        self.nodes_tree = {}
        self.nodes_list = []
        self.node_state = defaultdict(lambda: None)
        self.global_state = defaultdict(dict)
        self.plugin_dict = defaultdict(lambda: None)

        self._module_path_finder = ModulePathFinder()

        self._config_file = config_file
        self._config_dict = config_dict
        self._handle_signals = handle_signals

        self._bot_run_hooks = []
        self._bot_exit_hooks = []
        self._event_preprocessor_hooks = []
        self._event_postprocessor_hooks = []

        sys.meta_path.insert(0, self._module_path_finder)

        # self.chat_agent = ChatAgentExecutor(self)

    @property
    def nodes(self) -> list[type[Node[Any, Any, Any]]]:
        """当前已经加载的节点的列表。"""
        if self.nodes_tree and not self.nodes_list:
            self.nodes_list = flatten_tree_with_jumps(self.nodes_tree)

        return [_node for _node, _ in self.nodes_list]

    def run(self) -> None:
        """运行 SekaiBot。"""
        anyio.run(self.arun)

    async def arun(self) -> None:
        """异步运行 SekaiBot。"""
        self._restart_flag = True
        self._should_exit = anyio.Event()
        while self._restart_flag:
            self._restart_flag = False
            self._load_config_dict()
            await self.startup(init=True)
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._run)
                tg.start_soon(cancel_on_exit, self._should_exit, tg.cancel_scope)
                if self._handle_signals:  # pragma: no cover
                    tg.start_soon(self._handle_exit_signal)
            if self._restart_flag:
                self.nodes_loader._load_nodes_from_dirs(*self._extend_node_dirs)
                self.nodes_loader._load_nodes(*self._extend_nodes)

    def restart(self) -> None:
        """退出并重新运行 SekaiBot。"""
        logger.info("Restarting SekaiBot...")
        self._restart_flag = True
        self._should_exit.set()

    async def startup(self, init: bool = False) -> None:
        """加载或重加载 SekaiBot 的所有加载项"""

        self.nodes_tree.clear()
        self.nodes_list.clear()
        # 加载节点
        self.nodes_loader._load_nodes_from_dirs(*self.config.bot.node_dirs)
        self.nodes_loader._load_nodes(*self.config.bot.nodes)
        if not init:
            self.nodes_loader._load_nodes(*self._extend_nodes)
            self.nodes_loader._load_nodes_from_dirs(*self._extend_node_dirs)
        self._update_config()

    async def _run(self) -> None:
        """运行 SekaiBot。"""
        # 启动 SekaiBot
        logger.info("Running SekaiBot...")

        # 执行启动钩子
        for bot_run_hook_func in self._bot_run_hooks:
            await bot_run_hook_func(self)

        try:
            await self.manager.startup()
            from sekaibot.internal.event import Event

            class AEvent(Event):
                """"""

            async with anyio.create_task_group() as tg:
                tg.start_soon(self.manager.run)
                tg.start_soon(
                    self.manager.handle_event, AEvent(type="a_event", adapter="test_adapter")
                )
            """启动各种task
                _agent_task = asyncio.create_task(_agent.safe_run())
                self._agent_tasks.add(_agent_task)
                _agent_task.add_done_callback(self._agent_tasks.discard)
            """

            await self._should_exit.wait()
        finally:
            """执行结束方法
                结束各个任务
                while self._agent_tasks:
                    await asyncio.sleep(0)
            """
            await self.manager.shutdown()

            # 执行退出钩子
            for bot_exit_hook_func in self._bot_exit_hooks:
                await bot_exit_hook_func(self)

            self._module_path_finder.path.clear()

    async def _handle_exit_signal(self) -> None:  # pragma: no cover
        """根据平台不同注册信号处理程序。"""
        if threading.current_thread() is not threading.main_thread():
            # Signal 仅能在主线程中被处理
            return
        try:
            with anyio.open_signal_receiver(*HANDLED_SIGNALS) as signals:
                async for _signal in signals:
                    self.shutdown()
        except NotImplementedError:
            # add_signal_handler 仅在 Unix 下可用，以下对于 Windows
            for sig in HANDLED_SIGNALS:
                signal.signal(sig, self.shutdown)

    def shutdown(self, *_args: Any):
        """当机器人收到退出信号时，根据情况进行处理。"""
        logger.info("Stopping SekaiBot...")
        if self._should_exit.is_set():
            logger.warning("Force Exit SekaiBot...")
            sys.exit()
        else:
            self._should_exit.set()

    def _update_config(self) -> None:
        """更新 config，合并入来自 Node 和 Adapter 的 Config。"""

        def update_config(
            source: list[type[Node[Any, Any, Any]]],
            name: str,
            base: type[ConfigModel],
        ) -> tuple[type[ConfigModel], ConfigModel]:
            config_update_dict: dict[str, Any] = {}
            for i in source:
                config_class = getattr(i, "Config", None)
                if is_config_class(config_class):
                    default_value: Any
                    try:
                        default_value = config_class()
                    except ValidationError:
                        default_value = ...
                    config_update_dict[config_class.__config_name__] = (
                        config_class,
                        default_value,
                    )
            config_model = create_model(name, **config_update_dict, __base__=base)
            return config_model, config_model()

        self.config = create_model(
            "Config",
            node=update_config(self.nodes, "NodeConfig", NodeConfig),
            __base__=MainConfig,
        )(**self._raw_config_dict)

        configure_logging(self.config.bot.log.level, self.config.bot.log.verbose_exception)

    def _load_config_dict(self) -> None:
        """重新加载配置文件，支持 JSON / TOML / YAML 格式。"""
        self._raw_config_dict = {}

        if self._config_dict is not None:
            self._raw_config_dict = self._config_dict
        elif self._config_file is not None:
            try:
                with Path(self._config_file).open("rb") as f:
                    if self._config_file.endswith(".json"):
                        self._raw_config_dict = json.load(f)
                    elif self._config_file.endswith(".toml"):
                        self._raw_config_dict = tomllib.load(f)
                    elif self._config_file.endswith((".yml", ".yaml")):
                        self._raw_config_dict = yaml.safe_load(f)
                    else:
                        logger.error(
                            "Read config file failed: Unable to determine config file type"
                        )
            except OSError:
                logger.exception("Can not open config file:")
            except (ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError, yaml.YAMLError):
                logger.exception("Read config file failed:")

        try:
            self.config = MainConfig(**self._raw_config_dict)
        except ValidationError:
            self.config = MainConfig()
            logger.exception("Config dict parse error")

        self._update_config()

    def bot_run_hook(self, func: BotHook) -> BotHook:
        """注册一个 Bot 启动时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        self._bot_run_hooks.append(func)
        return func

    def bot_exit_hook(self, func: BotHook) -> BotHook:
        """注册一个 Bot 退出时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        self._bot_exit_hooks.append(func)
        return func

    def event_preprocessor_hook(self, func: EventHook) -> EventHook:
        """注册一个事件预处理函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        self._event_preprocessor_hooks.append(func)
        return func

    def event_postprocessor_hook(self, func: EventHook) -> EventHook:
        """注册一个事件后处理函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        self._event_postprocessor_hooks.append(func)
        return func


'''
    def get_session_id(self, event: dict):
        if is_private_message(event):
            return "user_" + str(event.get("user_id"))
        else:
            return "group_" + str(event.get("group_id"))

    def check_answer(self, event: dict) -> bool:
        
        if is_private_message(event):
            return True
        is_group = (event.get("message_type") == "group")
        group_keywords_hit = False
        if is_group:
            group_keywords_hit = check_group_keywords(event.get("plain_text", ""), self.config.keywords)
        return is_at_bot(event) or (is_group and group_keywords_hit)

    async def handle_message(self, event: dict) -> str | None:
        """
        核心消息处理入口：
        1. 判断是否需要回复：
        - 私聊 or (群聊且 at_bot==True) or (群聊且命中关键词)
        2. 如果需要回复，调用 LangChain Agent 获取回复并返回。
        3. 如果不需要回复，仅做消息存储，返回 None。
        """
        session_id = self.get_session_id(event)
        
        if not self.check_answer(event):
            await self.chat_agent.memory_manager.add_message(
                session_id=session_id,
                role="user",
                input=event.get("plain_text"),
                timestamp=int(event.get("time")),
                message_id=str(event.get("message_id"))
            )
            return None
        
        reply = (await self.chat_agent.run(
            message=event, 
            session_id=session_id,
            timestamp=int(event.get("time")),
            message_id=str(event.get("message_id")), 
        ))

        return reply'''


"""if __name__ == "__main__":
    # 示例：模拟私聊测试
    sample_event_private = {
        "type": "message",
        "time": 1738559871,
        "self_id": 3988189771,
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": 24495503,
        "user_id": 2122331,
        "plain_text": "我是谁",
        "user_name": "Miku",
        "ask_bot": True,
        "startwith_atbot": False
    }

    # 示例：模拟群聊测试
    sample_event_group = {
        "type": "message",
        "time": 1738559959,
        "self_id": 3988189771,
        "post_type": "message",
        "message_type": "group",
        "group_id": 89411261,
        "message_id": 1593257552,
        "user_id": 26820646331,
        "plain_text": "我叫什么名字",
        "user_name": "Miku",
        "ask_bot": False,
        "startwith_atbot": True
    }
    bot = Bot(Config())

    async def run_test():
        resp1 = await bot.handle_message(sample_event_private)
        print("私聊回复:", resp1)

        resp2 = await bot.handle_message(sample_event_group)
        print("群聊回复:", resp2)

    asyncio.run(run_test())"""
