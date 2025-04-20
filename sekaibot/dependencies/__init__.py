"""SekaiBot 依赖注入。

实现依赖注入相关功能。
"""

from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, TypeVar

from sekaibot.internal.event import Event
from sekaibot.typing import DependencyCacheT, GlobalStateT, NodeStateT, StateT

from .utils import Dependency, InnerDepends, solve_dependencies

if TYPE_CHECKING:
    from sekaibot.bot import Bot

_T = TypeVar("_T")


__all__ = [
    "Dependency",
    "Depends",
    "InnerDepends",
    "solve_dependencies",
    "solve_dependencies_in_bot",
]


def Depends(  # noqa: N802 # pylint: disable=invalid-name
    dependency: Dependency[_T] | None = None, *, use_cache: bool = True
) -> _T:
    """子依赖装饰器。

    Args:
        dependency: 依赖类。如果不指定则根据字段的类型注释自动判断。
        use_cache: 是否使用缓存。默认为 `True`。

    Returns:
        返回内部子依赖对象。
    """
    return InnerDepends(dependency=dependency, use_cache=use_cache)  # type: ignore


async def solve_dependencies_in_bot(
    dependent: Dependency[_T],
    *,
    bot: "Bot",
    event: Event[Any] | None = None,
    state: StateT | None = None,
    node_state: NodeStateT | None = None,
    global_state: GlobalStateT | None = None,
    use_cache: bool = True,
    stack: AsyncExitStack | None = None,
    dependency_cache: dict[Any, Any] | None = None,
) -> _T:
    """解析子依赖。

    此方法强制要求 `bot`、`event`、`state`、`global_state` 作为参数，以确保依赖解析的严谨性。

    Args:
        dependent: 需要解析的依赖。
        bot: 机器人实例，必须提供。
        event: 事件对象，必须提供。
        state: 节点临时的状态信息，默认为 `None`。
        node_state: 节点持久化状态信息，可选，默认为 `None`。
        global_state: 为节点提供的全局状态，可选，默认为 `None`。
        use_cache: 是否使用缓存，默认为 `True`。
        stack: 异步上下文管理器，可选。
        dependency_cache: 依赖缓存，如果未提供，则自动创建新字典。

    Returns:
        解析后的依赖对象。
    """
    from sekaibot.bot import Bot

    if not dependency_cache:
        dependency_cache = {}
    dependency_cache.update(
        {
            Bot: bot,
            "bot": bot,
            Event: event,
            "event": event,
            StateT: state,
            "state": state,
            GlobalStateT: global_state,
            "global_state": global_state,
            NodeStateT: node_state,
            "node_state": node_state,
        }
    )
    dependency_cache.update({DependencyCacheT: dependency_cache})
    return await solve_dependencies(
        dependent, use_cache=use_cache, stack=stack, dependency_cache=dependency_cache
    )
