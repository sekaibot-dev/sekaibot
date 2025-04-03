import pkgutil
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sekaibot.exceptions import LoadModuleError
from sekaibot.internal.node import Node, NodeLoadType
from sekaibot.log import logger
from sekaibot.utils import (
    ModuleType,
    flatten_tree_with_jumps,
    get_classes_from_module_name,
)

if TYPE_CHECKING:
    from sekaibot.bot import Bot


class NodesLoader:
    bot: "Bot"

    def __init__(self, bot: "Bot"):
        self.bot = bot

    def _load_node_classes(
        self,
        *nodes: tuple[type[Node[Any, Any, Any]], NodeLoadType, str | None],
    ) -> None:
        """加载节点类，并构建树"""
        # 构建节点字典
        nodes_dict: dict[str, type[Node[Any, Any, Any]]] = {
            _node.__name__: _node for _node in (self.bot.nodes or [])
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
        self.bot.nodes_tree = {root: build_tree(root) for root in roots}
        self.bot.nodes_list = flatten_tree_with_jumps(self.bot.nodes_tree)
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
                    for path in self.bot._module_path_finder.path:
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
        self.bot._extend_nodes.extend(nodes)
        return self._load_nodes(*nodes)

    def _load_nodes_from_dirs(self, *dirs: Path) -> None:
        """从目录中加载节点，以 `_` 开头的模块中的节点不会被导入。路径可以是相对路径或绝对路径。

        Args:
            *dirs: 储存包含节点的模块的模块路径。
                例如：`pathlib.Path("path/of/nodes/")` 。
        """
        dir_list = [str(x.resolve()) for x in dirs]
        logger.info("Loading nodes from dirs", dirs=", ".join(map(str, dir_list)))
        self.bot._module_path_finder.path.extend(dir_list)
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
        self.bot._extend_node_dirs.extend(dirs)
        self._load_nodes_from_dirs(*dirs)
