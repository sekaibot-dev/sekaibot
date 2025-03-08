import asyncio
import anyio
import signal
import pkgutil
import threading
import json
from collections import defaultdict
from itertools import chain
from config import ConfigModel, MainConfig, NodeConfig
from log import Logger
from core.agent_executor import ChatAgentExecutor
import sys
from pathlib import Path

from typing import (
    Optional,
    Dict,
    Tuple,
    List,
    Set,
    Any,
    Type,
    Callable,
    Awaitable,
    Union,
    DefaultDict
) # type: ignore

from .exceptions import (
    LoadModuleError,
)

from pydantic import (
    ValidationError,
    create_model,  # pyright: ignore[reportUnknownVariableType]
)
from .utils import (
    ModulePathFinder,
    ModuleType,
    TreeType,
    flatten_tree_with_jumps,
    get_classes_from_module_name,
    is_config_class,
    cancel_on_exit,
    samefile,
    validate_instance
)

from .node import Node, NodeLoadType
from .manager import NodeManager
from ._types import BotHook, EventHook

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

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

class Bot():

    config: MainConfig
    logger: Logger
    manager: NodeManager

    nodes_tree: TreeType[Type[Node[Any, Any, Any]]]
    nodes_list: List[Tuple[Type[Node[Any, Any, Any]], int]]
    global_state: Dict[Any, Any]

    _should_exit: anyio.Event
    _restart_flag: bool  # 重启标记    
    _module_path_finder: ModulePathFinder  # 用于查找 nodes 的模块元路径查找器
    _raw_config_dict: Dict[str, Any]  # 原始配置字典

    _config_file: str | None  # 配置文件
    _config_dict: Dict[str, Any] | None  # 配置
    _handle_signals: bool  # 是否处理信号

    _extend_nodes: List[
        Type[Node[Any, Any, Any]] | str | Path
    ]  # 使用 load_nodes() 方法程序化加载的节点列表
    _extend_node_dirs: List[
        Path
    ]  # 使用 load_nodes_from_dirs() 方法程序化加载的节点路径列表

    #钩子
    _bot_run_hooks: List[BotHook]
    _bot_exit_hooks: List[BotHook]
    _event_preprocessor_hooks: list[EventHook]
    _event_postprocessor_hooks: list[EventHook]

    def __init__(
        self,
        *,
        config_file: str | None = "config.toml",
        config_dict: Dict[str, Any] | None = None,
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
        self.logger = Logger(self)
        self.nodes_tree = {}
        self.nodes_list = []
        self.global_state = {}

        self._module_path_finder = ModulePathFinder()

        self._config_file = config_file
        self._config_dict = config_dict
        self._handle_signals = handle_signals

        self._bot_run_hooks = []
        self._bot_exit_hooks = []
        self._event_preprocessor_hooks = []
        self._event_postprocessor_hooks = []

        sys.meta_path.insert(0, self._module_path_finder)

        #self.chat_agent = ChatAgentExecutor(self)


    @property
    def nodes(self) -> List[Type[Node[Any, Any, Any]]]:
        """当前已经加载的节点的列表。"""
        if self.nodes_tree and not self.nodes_list:
            self.nodes_list = flatten_tree_with_jumps(self.nodes_tree)

        return [_node for _node, _ in self.nodes_list]
    
    def run(self) -> None:
        """运行 SekaiBot。"""
        anyio.run(self.arun())

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
                self._load_nodes_from_dirs(*self._extend_node_dirs)
                self._load_nodes(*self._extend_nodes)

    def restart(self) -> None:
        """退出并重新运行 SekaiBot。"""
        self.logger.info("Restarting SekaiBot...")
        self._restart_flag = True
        self._should_exit.set()

    async def startup(self, init: bool = False) -> None:
        """加载或重加载 SekaiBot 的所有加载项"""
        
        self.nodes_tree.clear()
        self.nodes_list.clear()
        # 加载节点
        self._load_nodes_from_dirs(*self.config.bot.node_dirs)
        self._load_nodes(*self.config.bot.nodes)
        if not init:
            self._load_nodes(*self._extend_nodes)
            self._load_nodes_from_dirs(*self._extend_node_dirs)
        self._update_config()

    async def _run(self) -> None:
        """运行 SekaiBot。"""
        # 启动 SekaiBot
        self.logger.info("Running SekaiBot...")

        #执行启动钩子
        for bot_run_hook_func in self._bot_run_hooks:
            await bot_run_hook_func(self)

        try:
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
        self.logger.info("Stopping SekaiBot...")
        if self._should_exit.is_set():
            self.logger.warning("Force Exit SekaiBot...")
            sys.exit()
        else:
            self._should_exit.set()
    
    def _update_config(self) -> None:
        """更新 config，合并入来自 Node 和 Adapter 的 Config。"""

        def update_config(
            source: List[Type[Node[Any, Any, Any]]],
            name: str,
            base: Type[ConfigModel],
        ) -> Tuple[Type[ConfigModel], ConfigModel]:
            config_update_dict: Dict[str, Any] = {}
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

        self.logger._reload_logger()

    def _load_config_dict(self) -> None:
        """重新加载配置文件。"""
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
                    else:
                        self.logger.error(
                            "Read config file failed: "
                            "Unable to determine config file type"
                        )
            except OSError:
                self.logger.exception("Can not open config file:")
            except (ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError):
                self.logger.exception("Read config file failed:")

        try:
            self.config = MainConfig(**self._raw_config_dict)
        except ValidationError:
            self.config = MainConfig()
            self.logger.exception("Config dict parse error")
        
        self._update_config()

    def _load_node_classes(
        self,
        *nodes: Tuple[Type[Node[Any, Any, Any]], NodeLoadType, str | None],
    ) -> None:
        """加载节点类，并构建树"""
        # 构建节点字典
        nodes_dict: Dict[str, Type[Node[Any, Any, Any]]] = {
            _node.__name__: _node for _node in (self.nodes or [])
        }
        for node_class, load_type, file_path in nodes:
            node_class.__node_load_type__ = load_type
            node_class.__node_file_path__ = file_path
            if node_class.__name__ in nodes_dict:
                self.logger.warning(
                    "Already have a same name node", 
                    name=node_class.__name__
                )
            nodes_dict[node_class.__name__] = node_class
        # 构建节点集合和根节点集合
        all_nodes = set(nodes_dict.values())
        roots = {
            _node for _node in all_nodes if not _node.parent
        }
        #构建 节点-子节点 映射表
        parent_map: DefaultDict[Type[Node[Any, Any, Any]], List[Type[Node[Any, Any, Any]]]] = defaultdict(list)
        for _node in all_nodes - roots:
            if _node.parent not in nodes_dict:
                self.logger.warning(
                    "Parent node not found",
                    parent_name=_node.parent,
                    node_name=_node.__name__,
                )
                continue
            parent_map[nodes_dict[_node.parent]].append(_node)
        #  递归建树
        def build_tree(
            node_class: Type[Node[Any, Any, Any]]
        ) -> Dict[str, Any]:
            return {
                child: build_tree(child) for child in parent_map[node_class]
            }
        # 加载到类属性
        self.nodes_tree = {root: build_tree(root) for root in roots}
        self.nodes_list = flatten_tree_with_jumps(self.nodes_tree)
        # 记录节点加载信息
        for _node, _, _ in nodes:
            self.logger.info(
                "Succeeded to load node from class",
                name=_node.__name__,
                node_class=_node,
            )

    def _load_nodes_from_module_name(
        self,
        *module_name: str,
        node_load_type: NodeLoadType,
        reload: bool = False,
    ) -> None:
        """从模块名称中节点模块。"""
        
        node_classes: List[Tuple[Type[Node], ModuleType]] = []
        for name in module_name:
            try:
                classes = get_classes_from_module_name(name, Node, reload=reload)
                node_classes.extend(classes)
            except ImportError as e:
                self.logger.exception("Import module failed", module_name=name)
        if node_classes:
            nodes = [(node_class, node_load_type, module.__file__) for node_class, module in node_classes]
            self._load_node_classes(*nodes)

    def _load_nodes(
        self,
        *nodes: Type[Node[Any, Any, Any]] | str | Path,
        node_load_type: NodeLoadType | None = None,
        reload: bool = False,
    ) -> None:
        """加载节点。

        Args:
            *nodes: 节点类、节点模块名称或者节点模块文件路径。类型可以是 `Type[Node]`, `str` 或 `pathlib.Path`。
                如果为 `Type[Node]` 类型时，将作为节点类进行加载。
                如果为 `str` 类型时，将作为节点模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.node`。
                如果为 `pathlib.Path` 类型时，将作为节点模块文件路径进行加载。
                    例如：`pathlib.Path("path/of/node")`。
            node_load_type: 节点加载类型，如果为 `None` 则自动判断，否则使用指定的类型。
            reload: 是否重新加载模块。
        """
        node_classes = []
        module_names = []
        
        for node_ in nodes:
            try:
                if isinstance(node_, type) and issubclass(node_, Node):
                    # 节点类直接加入列表
                    node_classes.append(node_)
                elif isinstance(node_, str):
                    # 字符串直接作为模块名称加入列表
                    self.logger.info("Loading nodes from module", module_name=node_)
                    module_names.append(node_)
                elif isinstance(node_, Path):
                    self.logger.info("Loading nodes from path", path=node_)
                    if not node_.is_file():
                        raise LoadModuleError(
                            f'The node path "{node_}" must be a file'
                        )
                    if node_.suffix != ".py":
                        raise LoadModuleError(
                            f'The path "{node_}" must endswith ".py"'
                        )
        
                    node_module_name = None
                    for path in self._module_path_finder.path:
                        try:
                            if node_.stem == "__init__":
                                if node_.resolve().parent.parent.samefile(Path(path)):
                                    node_module_name = node_.resolve().parent.name
                                    break
                            elif node_.resolve().parent.samefile(Path(path)):
                                node_module_name = node_.stem
                                break
                        except OSError:
                            continue
                    if node_module_name is None:
                        rel_path = node_.resolve().relative_to(Path().resolve())
                        if rel_path.stem == "__init__":
                            node_module_name = ".".join(rel_path.parts[:-1])
                        else:
                            node_module_name = ".".join(rel_path.parts[:-1] + (rel_path.stem,))
        
                    module_names.append(node_module_name)
                else:
                    raise TypeError(f"{node_} can not be loaded as node")
            except Exception:
                self.logger.exception("Load node failed:", node=node_)
        
        # 如果有节点类，则调用新的 _load_node_class 批量加载
        if node_classes:
            nodes = [(node_class, node_load_type or NodeLoadType.CLASS, None) for node_class in node_classes]
            self._load_node_classes(*nodes)
        
        # 如果有模块名称，则调用新的 _load_nodes_from_module_name 批量加载
        if module_names:
            self._load_nodes_from_module_name(
                *module_names,
                node_load_type=node_load_type or NodeLoadType.NAME,
                reload=reload
            )

    def load_nodes(
        self, *nodes: Type[Node[Any, Any, Any]] | str | Path
    ) -> None:
        """加载节点。

        Args:
            *nodes: 节点类、节点模块名称或者节点模块文件路径。
                类型可以是 `Type[Node]`, `str` 或 `pathlib.Path`。
                如果为 `Type[Node]` 类型时，将作为节点类进行加载。
                如果为 `str` 类型时，将作为节点模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.node`。
                如果为 `pathlib.Path` 类型时，将作为节点模块文件路径进行加载。
                    例如：`pathlib.Path("path/of/node")`。
        """
        self._extend_nodes.extend(nodes)
        return self._load_nodes(*nodes)

    def _load_nodes_from_dirs(self, *dirs: Path) -> None:
        """从目录中加载节点，以 `_` 开头的模块中的节点不会被导入。路径可以是相对路径或绝对路径。

        Args:
            *dirs: 储存包含节点的模块的模块路径。
                例如：`pathlib.Path("path/of/nodes/")` 。
        """
        dir_list = [str(x.resolve()) for x in dirs]
        self.logger.info("Loading nodes from dirs", dirs=", ".join(map(str, dir_list)))
        self._module_path_finder.path.extend(dir_list)
        module_name = list(
            filter(lambda name: not name.startswith("_"), 
                (module_info.name for module_info in pkgutil.iter_modules(dir_list)))
        )
        self._load_nodes_from_module_name(
            *module_name, node_load_type=NodeLoadType.DIR
        )

    def load_nodes_from_dirs(self, *dirs: Path) -> None:
        """从目录中加载节点，以 `_` 开头的模块中的节点不会被导入。路径可以是相对路径或绝对路径。

        Args:
            *dirs: 储存包含节点的模块的模块路径。
                例如：`pathlib.Path("path/of/nodes/")` 。
        """
        self._extend_node_dirs.extend(dirs)
        self._load_nodes_from_dirs(*dirs)


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

    async def handle_message(self, event: dict) -> Optional[str]:
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

        return reply

    

'''if __name__ == "__main__":
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

    asyncio.run(run_test())'''
