import inspect
import json
import pkgutil
import signal
import sys
import threading
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any, ClassVar, overload

import anyio
import yaml
from exceptiongroup import catch
from pydantic import ValidationError, create_model  # pyright: ignore[reportUnknownVariableType]

from sekaibot.config import AdapterConfig, ConfigModel, MainConfig, NodeConfig, PluginConfig
from sekaibot.dependencies import solve_dependencies
from sekaibot.exceptions import LoadModuleError, SkipException
from sekaibot.internal.adapter import Adapter
from sekaibot.internal.node import Node, NodeLoadType
from sekaibot.internal.node.manager import NodeManager
from sekaibot.log import configure_logging, logger
from sekaibot.plugin import Plugin
from sekaibot.typing import AdapterHook, AdapterT, BotHook, EventHook, NodeHook
from sekaibot.utils import (
    ModulePathFinder,
    ModuleType,
    TreeType,
    cancel_on_exit,
    flatten_tree_with_jumps,
    get_classes_from_module_name,
    handle_exception,
    is_config_class,
    run_coro_with_catch,
)

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)

__all__ = [
    "Bot",
]


class Bot:
    config: MainConfig
    manager: NodeManager

    adapters: list[Adapter[Any, Any]]
    nodes_tree: TreeType[type[Node[Any, Any, Any]]]
    nodes_list: list[tuple[type[Node[Any, Any, Any]], int]]
    node_state: dict[str, Any]
    plugin_dict: dict[str, Plugin[Any]]
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
    _extend_adapters: list[
        type[Adapter[Any, Any]] | str
    ]  # 使用 load_adapter() 方法程序化加载的适配器列表
    _extend_plugins: ClassVar[
        list[
            tuple[type[Plugin[Any]], bool]  # | str | Path
        ]
    ] = []

    _bot_startup_hooks: ClassVar[set[BotHook]] = set()
    _bot_run_hooks: ClassVar[set[BotHook]] = set()
    _bot_exit_hooks: ClassVar[set[BotHook]] = set()
    _adapter_startup_hooks: ClassVar[set[AdapterHook]] = set()
    _adapter_run_hooks: ClassVar[set[AdapterHook]] = set()
    _adapter_shutdown_hooks: ClassVar[set[AdapterHook]] = set()
    _event_preprocessor_hooks: ClassVar[set[EventHook]] = set()
    _event_postprocessor_hooks: ClassVar[set[EventHook]] = set()
    _node_preprocessor_hooks: ClassVar[set[NodeHook]] = set()
    _node_postprocessor_hooks: ClassVar[set[NodeHook]] = set()

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
        self.nodes_tree = {}
        self.nodes_list = []
        self.node_state = defaultdict(lambda: None)
        self.adapters = []
        self.plugin_dict = defaultdict(lambda: None)
        self.global_state = defaultdict(dict)

        self._restart_flag = False
        self._module_path_finder = ModulePathFinder()
        self._extend_nodes = []
        self._extend_node_dirs = []
        self._extend_adapters = []

        self._config_file = config_file
        self._config_dict = config_dict
        self._raw_config_dict = {}
        self._handle_signals = handle_signals

        sys.meta_path.insert(0, self._module_path_finder)

    async def _run_bot_hooks(self, hooks: list[BotHook], name: str):
        if not hooks:
            return

        logger.debug(f"Running {name}...")

        with catch({Exception: handle_exception(f"Error when running {name}")}):
            async with anyio.create_task_group() as tg:
                for hook_func in hooks:
                    tg.start_soon(
                        run_coro_with_catch,
                        solve_dependencies(
                            hook_func,
                            dependency_cache={
                                Bot: self,
                                "bot": self,
                            },
                        ),
                        (SkipException,),
                    )

    async def _run_adapter_hooks(
        self,
        hooks: list[AdapterHook],
        adapter: Adapter[Any, Any],
        name: str,
    ):
        if not hooks:
            return

        logger.debug(f"Running {name}...", adapter=adapter)

        with catch({Exception: handle_exception(f"Error when running {name}")}, adapter=adapter):
            async with anyio.create_task_group() as tg:
                for hook_func in hooks:
                    tg.start_soon(
                        run_coro_with_catch,
                        solve_dependencies(
                            hook_func,
                            dependency_cache={
                                Adapter: adapter,
                                "adapter": adapter,
                                Bot: self,
                                "bot": self,
                            },
                        ),
                        (SkipException,),
                    )

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
            await self.startup()
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._run)
                tg.start_soon(cancel_on_exit, self._should_exit, tg.cancel_scope)
                if self._handle_signals:  # pragma: no cover
                    tg.start_soon(self._handle_exit_signal)
            if self._restart_flag:
                self._load_nodes(*self._extend_nodes)
                self._load_nodes_from_dirs(*self._extend_node_dirs)
                self._load_adapters(*self._extend_adapters)
                self.load_plugins()

    def restart(self) -> None:
        """退出并重新运行 SekaiBot。"""
        logger.info("Restarting SekaiBot...")
        self._restart_flag = True
        self._should_exit.set()

    async def startup(self) -> None:
        """加载或重加载 SekaiBot 的所有加载项"""

        self.nodes_tree.clear()
        self.nodes_list.clear()

        self._load_nodes_from_dirs(*self.config.bot.node_dirs)
        self._load_nodes(*self.config.bot.nodes)
        self._load_adapters(*self.config.bot.adapters)
        self.load_plugins()

        await self._run_bot_hooks(self._bot_startup_hooks, "BotStartupHooks")

        self._update_config()

    async def _run(self) -> None:
        """运行 SekaiBot。"""
        # 启动 SekaiBot
        logger.info("Running SekaiBot...")

        await self._run_bot_hooks(self._bot_run_hooks, "BotRunHooks")

        try:
            for _adapter in self.adapters:
                await self._run_adapter_hooks(
                    self._adapter_startup_hooks, _adapter, "AdapterStartupHooks"
                )
                try:
                    await _adapter.startup()
                except Exception:
                    logger.exception("Startup adapter failed", adapter=_adapter)

            try:
                await self.manager.startup()
            except Exception:
                logger.exception("Startup manager failed", manager=self.manager)

            async with anyio.create_task_group() as tg:
                for _adapter in self.adapters:
                    await self._run_adapter_hooks(
                        self._adapter_run_hooks, _adapter, "AdapterRunHooks"
                    )
                    tg.start_soon(_adapter.safe_run)

                tg.start_soon(self.manager.run)

        finally:
            for _adapter in self.adapters:
                await self._run_adapter_hooks(
                    self._adapter_shutdown_hooks, _adapter, "AdapterShutdownHooks"
                )
                await _adapter.shutdown()

            await self.manager.shutdown()

            await self._run_bot_hooks(self._bot_exit_hooks, "BotExitHooks")

            self.nodes_tree.clear()
            self.nodes_list.clear()
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
            plugin=update_config(list(self.plugin_dict.values()), "PluginConfig", PluginConfig),
            adapter=update_config(self.adapters, "AdapterConfig", AdapterConfig),
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

    def _load_node_classes(
        self,
        *nodes: tuple[type[Node[Any, Any, Any]], NodeLoadType, str | None],
    ) -> None:
        """加载节点类，并构建树"""
        # 构建节点字典
        nodes_dict: dict[str, type[Node[Any, Any, Any]]] = {
            _node.__name__: _node for _node in (self.nodes or [])
        }
        for node_class, load_type, file_path in nodes:
            node_class.__node_load_type__ = load_type
            node_class.__node_file_path__ = file_path
            if node_class.__name__ in nodes_dict:
                logger.warning("Already have a same name node", name=node_class.__name__)
            nodes_dict[node_class.__name__] = node_class
        # 构建节点集合和根节点集合
        all_nodes = set(nodes_dict.values())
        roots = [_node for _node in all_nodes if not _node.parent]
        # 构建 节点-子节点 映射表
        parent_map: defaultdict[type[Node[Any, Any, Any]], list[type[Node[Any, Any, Any]]]] = (
            defaultdict(list)
        )
        for _node in all_nodes - set(roots):
            if _node.parent not in nodes_dict:
                logger.warning(
                    "Parent node not found",
                    parent_name=_node.parent,
                    node_name=_node.__name__,
                )
                _node.parent = None
                roots.append(_node)
                continue
            parent_map[nodes_dict[_node.parent]].append(_node)
        roots.sort(key=lambda _node: getattr(_node, "priority", 0))

        #  递归建树
        def build_tree(node_class: type[Node[Any, Any, Any]]) -> dict[str, Any]:
            return {
                child: build_tree(child)
                for child in sorted(
                    parent_map[node_class], key=lambda _node: getattr(_node, "priority", 0)
                )
            }

        # 加载到类属性
        self.nodes_tree = {root: build_tree(root) for root in roots}
        self.nodes_list = flatten_tree_with_jumps(self.nodes_tree)
        # 记录节点加载信息
        for _node, _, _ in nodes:
            logger.info(
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
        node_classes: list[tuple[type[Node], ModuleType]] = []
        for name in module_name:
            try:
                classes = get_classes_from_module_name(name, Node, reload=reload)
                node_classes.extend(classes)
            except ImportError:
                logger.exception("Import module failed", module_name=name)
        if node_classes:
            nodes = [
                (node_class, node_load_type, module.__file__)
                for node_class, module in node_classes
                if node_class.load
            ]
            self._load_node_classes(*nodes)

    def _load_nodes(
        self,
        *nodes: type[Node[Any, Any, Any]] | str | Path,
        node_load_type: NodeLoadType | None = None,
        reload: bool = False,
    ) -> None:
        """加载节点。

        Args:
            *nodes: 节点类、节点模块名称或者节点模块文件路径。类型可以是 `type[Node]`, `str` 或 `pathlib.Path`。
                如果为 `type[Node]` 类型时，将作为节点类进行加载。
                如果为 `str` 类型时，将作为节点模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.node`。
                如果为 `pathlib.Path` 类型时，将作为节点模块文件路径进行加载。
                    例如：`pathlib.Path("path/of/node")`。
            node_load_type: 节点加载类型，如果为 `None` 则自动判断，否则使用指定的类型。
            reload: 是否重新加载模块。
        """
        node_classes: list[type[Node[Any, Any, Any]]] = []
        module_names: list[str] = []

        for node_ in nodes:
            try:
                if isinstance(node_, type) and issubclass(node_, Node):
                    # 节点类直接加入列表
                    node_classes.append(node_)
                elif isinstance(node_, str):
                    # 字符串直接作为模块名称加入列表
                    logger.info("Loading nodes from module", module_name=node_)
                    module_names.append(node_)
                elif isinstance(node_, Path):
                    logger.info("Loading nodes from path", path=node_)
                    if not node_.is_file():
                        raise LoadModuleError(f'The node path "{node_}" must be a file')
                    if node_.suffix != ".py":
                        raise LoadModuleError(f'The path "{node_}" must endswith ".py"')

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
                logger.exception("Load node failed:", node=node_)

        # 如果有节点类，则调用新的 _load_node_class 批量加载
        if node_classes:
            nodes = [
                (node_class, node_load_type or NodeLoadType.CLASS, None)
                for node_class in node_classes
                if node_class.load
            ]
            self._load_node_classes(*nodes)

        # 如果有模块名称，则调用新的 _load_nodes_from_module_name 批量加载
        if module_names:
            self._load_nodes_from_module_name(
                *module_names, node_load_type=node_load_type or NodeLoadType.NAME, reload=reload
            )

    def load_nodes(self, *nodes: type[Node[Any, Any, Any]] | str | Path) -> None:
        """加载节点。

        Args:
            *nodes: 节点类、节点模块名称或者节点模块文件路径。
                类型可以是 `type[Node]`, `str` 或 `pathlib.Path`。
                如果为 `type[Node]` 类型时，将作为节点类进行加载。
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
        logger.info("Loading nodes from dirs", dirs=", ".join(map(str, dir_list)))
        self._module_path_finder.path.extend(dir_list)
        module_name = list(
            filter(
                lambda name: not name.startswith("_"),
                (module_info.name for module_info in pkgutil.iter_modules(dir_list)),
            )
        )
        self._load_nodes_from_module_name(*module_name, node_load_type=NodeLoadType.DIR)

    def load_nodes_from_dirs(self, *dirs: Path) -> None:
        """从目录中加载节点，以 `_` 开头的模块中的节点不会被导入。路径可以是相对路径或绝对路径。

        Args:
            *dirs: 储存包含节点的模块的模块路径。
                例如：`pathlib.Path("path/of/nodes/")` 。
        """
        self._extend_node_dirs.extend(dirs)
        self._load_nodes_from_dirs(*dirs)

    def get_node(self, name: str) -> type[Node[Any, Any, Any]]:
        """按照名称获取已经加载的插件类。

        Args:
            name: 插件名称

        Returns:
            获取到的插件类。

        Raises:
            LookupError: 找不到此名称的插件类。
        """
        for _plugin in self.nodes:
            if _plugin.__name__ == name:
                return _plugin
        raise LookupError(f'Can not find node named "{name}"')

    def load_plugins(self):
        """加载插件。"""
        for plugin_class, _reload in self._extend_plugins:
            try:
                if plugin_class.name not in self.plugin_dict or _reload:
                    _plugin = plugin_class(self)
                    self.plugin_dict[plugin_class.name] = _plugin
                    logger.info(
                        "Succeeded to load plugin from class",
                        name=_plugin.name,
                        plugin=_plugin,
                    )
            except Exception:
                logger.exception("Load plugin failed:", plugin=_plugin)

    def get_plugin(self, name: str):
        """按照名称获取已经加载的插件类。

        Args:
            name: 插件名称

        Returns:
            获取到的插件类。

        Raises:
            LookupError: 找不到此名称的插件类。
        """
        if _plugin := self.plugin_dict.get(name):
            return _plugin
        raise LookupError(f'Can not find plugin named "{name}"')

    def _load_adapters(self, *adapters: type[Adapter[Any, Any]] | str) -> None:
        """加载适配器。

        Args:
            *adapters: 适配器类或适配器名称，类型可以是 `Type[Adapter]` 或 `str`。
                如果为 `Type[Adapter]` 类型时，将作为适配器类进行加载。
                如果为 `str` 类型时，将作为适配器模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.adapter`。
        """
        for adapter_ in adapters:
            adapter_object: Adapter[Any, Any]
            try:
                if isinstance(adapter_, type) and issubclass(adapter_, Adapter):
                    adapter_object = adapter_(self)
                    logger.info(
                        "Succeeded to load adapter from class",
                        name=adapter_object.__class__.__name__,
                        adapter_class=adapter_,
                    )
                elif isinstance(adapter_, str):
                    adapter_classes = get_classes_from_module_name(adapter_, Adapter)
                    if not adapter_classes:
                        raise LoadModuleError(  # noqa: TRY301
                            f"Can not find Adapter class in the {adapter_} module"
                        )
                    if len(adapter_classes) > 1:
                        raise LoadModuleError(  # noqa: TRY301
                            f"More then one Adapter class in the {adapter_} module"
                        )
                    adapter_object = adapter_classes[0][0](self)  # type: ignore
                    logger.info(
                        "Succeeded to load adapter from module",
                        name=adapter_object.__class__.__name__,
                        module_name=adapter_,
                    )
                else:
                    raise TypeError(  # noqa: TRY301
                        f"{adapter_} can not be loaded as adapter"
                    )
            except Exception:
                logger.exception("Load adapter failed", adapter=adapter_)
            else:
                self.adapters.append(adapter_object)

    def load_adapters(self, *adapters: type[Adapter[Any, Any]] | str) -> None:
        """加载适配器。

        Args:
            *adapters: 适配器类或适配器名称，类型可以是 `Type[Adapter]` 或 `str`。
                如果为 `Type[Adapter]` 类型时，将作为适配器类进行加载。
                如果为 `str` 类型时，将作为适配器模块名称进行加载，格式和 Python `import` 语句相同。
                    例如：`path.of.adapter`。
        """
        self._extend_adapters.extend(adapters)
        self._load_adapters(*adapters)

    @overload
    def get_adapter(self, adapter: str) -> Adapter[Any, Any]: ...

    @overload
    def get_adapter(self, adapter: type[AdapterT]) -> AdapterT: ...

    def get_adapter(self, adapter: str | type[AdapterT]) -> Adapter[Any, Any] | AdapterT:
        """按照名称或适配器类获取已经加载的适配器。

        Args:
            adapter: 适配器名称或适配器类。

        Returns:
            获取到的适配器对象。

        Raises:
            LookupError: 找不到此名称的适配器对象。
        """
        for _adapter in self.adapters:
            if isinstance(adapter, str):
                if _adapter.name == adapter:
                    return _adapter
            elif isinstance(_adapter, adapter):
                return _adapter
        raise LookupError(f'Can not find adapter named "{adapter}"')

    @classmethod
    def require_plugin(cls, plugin_class: type[Plugin], *, reload: bool = False):
        """声明依赖插件。

        Args:
            name: 插件模块名或插件标识符，仅在已声明插件的情况下可使用标识符。

        异常:
            RuntimeError: 插件无法加载
        """
        if (
            inspect.isclass(plugin_class)
            and issubclass(plugin_class, Plugin)
            and plugin_class != Plugin
        ):
            if plugin_class not in cls._extend_plugins:
                cls._extend_plugins.append((plugin_class, reload))
            elif reload:
                cls._extend_plugins[cls._extend_plugins.index(plugin_class)] = (
                    plugin_class,
                    reload,
                )
        else:
            logger.error("Require plugin failed: Not a plugin class", plugin_class=plugin_class)

    @classmethod
    def bot_startup_hook(cls, func: BotHook) -> BotHook:
        """注册一个 Bot 初始化时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._bot_startup_hooks.add(func)
        return func

    @classmethod
    def bot_run_hook(cls, func: BotHook) -> BotHook:
        """注册一个 Bot 启动时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._bot_run_hooks.add(func)
        return func

    @classmethod
    def bot_exit_hook(cls, func: BotHook) -> BotHook:
        """注册一个 Bot 退出时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._bot_exit_hooks.add(func)
        return func

    @classmethod
    def adapter_startup_hook(cls, func: AdapterHook) -> AdapterHook:
        """注册一个适配器初始化时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._adapter_startup_hooks.add(func)
        return func

    @classmethod
    def adapter_run_hook(cls, func: AdapterHook) -> AdapterHook:
        """注册一个适配器运行时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._adapter_run_hooks.add(func)
        return func

    @classmethod
    def adapter_shutdown_hook(cls, func: AdapterHook) -> AdapterHook:
        """注册一个适配器关闭时的函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._adapter_shutdown_hooks.add(func)
        return func

    @classmethod
    def event_preprocessor_hook(cls, func: EventHook) -> EventHook:
        """注册一个事件预处理函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._event_preprocessor_hooks.add(func)
        return func

    @classmethod
    def event_postprocessor_hook(cls, func: EventHook) -> EventHook:
        """注册一个事件后处理函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._event_postprocessor_hooks.add(func)
        return func

    @classmethod
    def node_preprocessor_hook(cls, func: NodeHook) -> NodeHook:
        """注册一个节点运行预处理函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._node_preprocessor_hooks.add(func)
        return func

    @classmethod
    def node_postprocessor_hook(cls, func: NodeHook) -> NodeHook:
        """注册一个节点运行后处理函数。

        Args:
            func: 被注册的函数。

        Returns:
            被注册的函数。
        """
        cls._node_postprocessor_hooks.add(func)
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
