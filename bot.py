import asyncio
import signal
import pkgutil
import threading
import json
from collections import defaultdict
from itertools import chain
from config import ConfigModel, MainConfig
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
    get_classes_from_module_name,
    is_config_class,
    samefile,
    validate_instance
)

from .plugin import Plugin, PluginLoadType
from ._types import BotHook

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
    should_exit: asyncio.Event
    plugins_tree: Dict[int, List[Type[Plugin[Any, Any, Any]]]]
    plugin_state: Dict[str, Any]
    global_state: Dict[Any, Any]

    _condition: asyncio.Condition

    _module_path_finder: ModulePathFinder  # 用于查找 plugins 的模块元路径查找器
    _raw_config_dict: Dict[str, Any]  # 原始配置字典

    _config_file: str | None  # 配置文件
    _config_dict: Dict[str, Any] | None  # 配置

    _extend_plugins: List[
        Type[Plugin[Any, Any, Any]] | str | Path
    ]  # 使用 load_plugins() 方法程序化加载的插件列表
    _extend_plugin_dirs: List[
        Path
    ]  # 使用 load_plugins_from_dirs() 方法程序化加载的插件路径列表

    #钩子
    _bot_run_hooks: List[BotHook]
    _bot_exit_hooks: List[BotHook]

    def __init__(
        self,
        *,
        config_file: str | None = "config.toml",
        config_dict: Dict[str, Any] | None = None,
    ):
        """初始化 SekaiBot，读取配置文件，创建配置。

        Args:
            config_file: 配置文件，如不指定则使用默认的 `config.toml`。
                若指定为 `None`，则不加载配置文件。
            config_dict: 配置字典，默认为 `None。`
                若指定字典，则会忽略 `config_file` 配置，不再读取配置文件。
        """
        self.config = MainConfig()
        self.logger = Logger(self)
        self.plugins_tree = defaultdict(list)
        self.plugin_state = defaultdict(lambda: None)
        self.global_state = {}

        self._module_path_finder = ModulePathFinder()

        self._config_file = config_file
        self._config_dict = config_dict

        self._config_file = config_file
        self._config_dict = config_dict

        self._bot_run_hooks = []
        self._bot_exit_hooks = []

        sys.meta_path.insert(0, self._module_path_finder)

        #self.chat_agent = ChatAgentExecutor(self)

    @property
    def plugins(self) -> List[Type[Plugin[Any, Any, Any]]]:
        """当前已经加载的插件的列表。"""
        return list(chain(*self.plugins_tree.values()))

    def run(self) -> None:
        """启动 SekaiBot，读取配置文件并执行 bot 逻辑。"""
        asyncio.run(self._run())

    async def _run(self) -> None:
        self.should_exit = asyncio.Event()
        self._condition = asyncio.Condition()

        # 监听并拦截系统退出信号，从而完成一些善后工作后再关闭程序
        if threading.current_thread() is threading.main_thread():  # pragma: no cover
            # Signal 仅能在主线程中被处理。
            try:
                loop = asyncio.get_running_loop()
                for sig in HANDLED_SIGNALS:
                    loop.add_signal_handler(sig, self._handle_exit)
            except NotImplementedError:
                # add_signal_handler 仅在 Unix 下可用，以下对于 Windows。
                for sig in HANDLED_SIGNALS:
                    signal.signal(sig, self._handle_exit)

        # 加载配置文件
        self._reload_config_dict()

        # 启动 KafuBot
        self.logger.info("Running KafuBot...")

        #执行启动钩子
        for bot_run_hook_func in self._bot_run_hooks:
            await bot_run_hook_func(self)

        try:
            """启动各种task
                _agent_task = asyncio.create_task(_agent.safe_run())
                self._agent_tasks.add(_agent_task)
                _agent_task.add_done_callback(self._agent_tasks.discard)
            """

            await self.should_exit.wait()

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
        
    def _handle_exit(self, *_args: Any):
        """当机器人收到退出信号时，根据情况进行处理。"""
        self.logger.info("Stopping KafuBot...")
        if self.should_exit.is_set():
            self.logger.warning("Force Exit KafuBot...")
            sys.exit()
        else:
            self.should_exit.set()
    
    def _update_config(self) -> None:
        """更新 config，合并入来自 Plugin 和 Adapter 的 Config。"""

        def update_config(
            source: List[Any],
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
            #plugin=update_config(self.plugins, "PluginConfig", PluginConfig),
            #adapter=update_config(self.adapters, "AdapterConfig", AdapterConfig),
            __base__=MainConfig,
        )(**self._raw_config_dict)

        self.logger._load_logger()

    def _reload_config_dict(self) -> None:
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

    def _load_plugin_class(
        self,
        *plugin_class: Type[Plugin[Any, Any, Any]],
        plugin_load_type: PluginLoadType,
        plugin_file_path: str | None,
    ) -> None:
        """加载插件类。"""
        '''priority = getattr(plugin_class, "priority", None)
        if isinstance(priority, int) and priority >= 0:
            for _plugin in self.plugins:
                if _plugin.__name__ == plugin_class.__name__:
                    self.logger.warning(
                        "Already have a same name plugin", name=_plugin.__name__
                    )
            plugin_class.__plugin_load_type__ = plugin_load_type
            plugin_class.__plugin_file_path__ = plugin_file_path
            #self.plugins_tree[priority].append(plugin_class)
            self.logger.info(
                "Succeeded to load plugin from class",
                name=plugin_class.__name__,
                plugin_class=plugin_class,
            )
        else:
            self.logger.error(
                "Load plugin from class failed: Plugin priority incorrect in the class",
                plugin_class=plugin_class,
            )'''

    def _load_plugins_from_module_name(
        self,
        *module_name: str,
        plugin_load_type: PluginLoadType,
        reload: bool = False,
    ) -> None:
        """从模块名称中插件模块。"""
        
        plugin_classes: List[Tuple[Type[Plugin], ModuleType]] = []
        for name in module_name:
            try:
                classes = get_classes_from_module_name(name, Plugin, reload=reload)
                plugin_classes.extend(classes)
            except ImportError as e:
                self.logger.exception("Import module failed", module_name=name)
        if plugin_classes:
            for plugin_class, module in plugin_classes:
                self._load_plugin_class(
                    plugin_class,  # type: ignore
                    plugin_load_type,
                    module.__file__,
                )

    def _load_plugins(
        self,
        *plugins: Type[Plugin[Any, Any, Any]] | str | Path,
        plugin_load_type: PluginLoadType | None = None,
        reload: bool = False,
    ) -> None:
        """加载插件。

        Args:
            *plugins: 插件类、插件模块名称或者插件模块文件路径。类型可以是 `Type[Plugin]`, `str` 或 `pathlib.Path`。
                如果为 `Type[Plugin]` 类型时，将作为插件类进行加载。
                如果为 `str` 类型时，将作为插件模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.plugin`。
                如果为 `pathlib.Path` 类型时，将作为插件模块文件路径进行加载。
                    例如：`pathlib.Path("path/of/plugin")`。
            plugin_load_type: 插件加载类型，如果为 `None` 则自动判断，否则使用指定的类型。
            reload: 是否重新加载模块。
        """
        plugin_classes = []
        module_names = []
        
        for plugin_ in plugins:
            try:
                if isinstance(plugin_, type) and issubclass(plugin_, Plugin):
                    # 插件类直接加入列表
                    plugin_classes.append(plugin_)
                elif isinstance(plugin_, str):
                    # 字符串直接作为模块名称加入列表
                    self.logger.info("Loading plugins from module", module_name=plugin_)
                    module_names.append(plugin_)
                elif isinstance(plugin_, Path):
                    self.logger.info("Loading plugins from path", path=plugin_)
                    if not plugin_.is_file():
                        raise LoadModuleError(
                            f'The plugin path "{plugin_}" must be a file'
                        )
                    if plugin_.suffix != ".py":
                        raise LoadModuleError(
                            f'The path "{plugin_}" must endswith ".py"'
                        )
        
                    plugin_module_name = None
                    for path in self._module_path_finder.path:
                        try:
                            if plugin_.stem == "__init__":
                                if plugin_.resolve().parent.parent.samefile(Path(path)):
                                    plugin_module_name = plugin_.resolve().parent.name
                                    break
                            elif plugin_.resolve().parent.samefile(Path(path)):
                                plugin_module_name = plugin_.stem
                                break
                        except OSError:
                            continue
                    if plugin_module_name is None:
                        rel_path = plugin_.resolve().relative_to(Path().resolve())
                        if rel_path.stem == "__init__":
                            plugin_module_name = ".".join(rel_path.parts[:-1])
                        else:
                            plugin_module_name = ".".join(rel_path.parts[:-1] + (rel_path.stem,))
        
                    module_names.append(plugin_module_name)
                else:
                    raise TypeError(f"{plugin_} can not be loaded as plugin")
            except Exception:
                self.logger.exception("Load plugin failed:", plugin=plugin_)
        
        # 如果有插件类，则调用新的 _load_plugin_class 批量加载
        if plugin_classes:
            self._load_plugin_class(
                *plugin_classes,
                plugin_load_type=plugin_load_type or PluginLoadType.CLASS,
                plugin_file_path=None
            )
        
        # 如果有模块名称，则调用新的 _load_plugins_from_module_name 批量加载
        if module_names:
            self._load_plugins_from_module_name(
                *module_names,
                plugin_load_type=plugin_load_type or PluginLoadType.NAME,
                reload=reload
            )

    def load_plugins(
        self, *plugins: Type[Plugin[Any, Any, Any]] | str | Path
    ) -> None:
        """加载插件。

        Args:
            *plugins: 插件类、插件模块名称或者插件模块文件路径。
                类型可以是 `Type[Plugin]`, `str` 或 `pathlib.Path`。
                如果为 `Type[Plugin]` 类型时，将作为插件类进行加载。
                如果为 `str` 类型时，将作为插件模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.plugin`。
                如果为 `pathlib.Path` 类型时，将作为插件模块文件路径进行加载。
                    例如：`pathlib.Path("path/of/plugin")`。
        """
        self._extend_plugins.extend(plugins)
        return self._load_plugins(*plugins)

    def _load_plugins_from_dirs(self, *dirs: Path) -> None:
        """从目录中加载插件，以 `_` 开头的模块中的插件不会被导入。路径可以是相对路径或绝对路径。

        Args:
            *dirs: 储存包含插件的模块的模块路径。
                例如：`pathlib.Path("path/of/plugins/")` 。
        """
        dir_list = [str(x.resolve()) for x in dirs]
        self.logger.info("Loading plugins from dirs", dirs=", ".join(map(str, dir_list)))
        self._module_path_finder.path.extend(dir_list)
        module_name = list(
            filter(lambda name: not name.startswith("_"), 
                (module_info.name for module_info in pkgutil.iter_modules(dir_list)))
        )
        self._load_plugins_from_module_name(
            *module_name, plugin_load_type=PluginLoadType.DIR
        )

    def load_plugins_from_dirs(self, *dirs: Path) -> None:
        """从目录中加载插件，以 `_` 开头的模块中的插件不会被导入。路径可以是相对路径或绝对路径。

        Args:
            *dirs: 储存包含插件的模块的模块路径。
                例如：`pathlib.Path("path/of/plugins/")` 。
        """
        self._extend_plugin_dirs.extend(dirs)
        self._load_plugins_from_dirs(*dirs)


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
