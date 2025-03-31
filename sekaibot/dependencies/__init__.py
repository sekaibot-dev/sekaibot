"""SekaiBot 依赖注入。

实现依赖注入相关功能。
"""

from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, TypeVar

from sekaibot.internal.event import Event
from sekaibot.typing import (
    DependencyCacheT,
    GlobalStateT,
    NodeStateT,
    StateT,
)

from .utils import Dependency, InnerDepends, solve_dependencies

if TYPE_CHECKING:
    from sekaibot.bot import Bot

_T = TypeVar("_T")


__all__ = [
    "Depends",
    "Dependency",
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


DependencyT = TypeVar("DependencyT", bound="Dependency")


def Import(dependency: DependencyT | None = None, *, use_cache: bool = True) -> DependencyT:
    """子依赖装饰器，返回对象依赖对象封装后的类本身。

    Args:
        dependency: 依赖类。如果不指定则根据字段的类型注释自动判断。
        use_cache: 是否使用缓存。默认为 `True`。

    Returns:
        对象的依赖对象封装后的类本身。
    """
    from sekaibot.bot import Bot
    def wrap(
        bot: Bot,
        event: Event,
        state: StateT,
        node_state: NodeStateT,
        global_state: GlobalStateT,
        dependency_cache: DependencyCacheT,
    ) -> DependencyT:
        async def util():
            return await solve_dependencies_in_bot(
                dependency,
                bot=bot,
                event=event,
                state=state,
                node_state=node_state,
                global_state=global_state,
                use_cache=use_cache,
                dependency_cache=dependency_cache,
            )

        return util

    return Depends(wrap, use_cache=use_cache)


async def solve_dependencies_in_bot(
    dependent: Dependency[_T],
    *,
    bot: "Bot",
    event: Event,
    state: StateT | None = None,
    node_state: NodeStateT | None = None,
    global_state: GlobalStateT | None = None,
    use_cache: bool = True,
    stack: AsyncExitStack | None = None,
    dependency_cache: DependencyCacheT | None = None,
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

    if dependency_cache is None:
        dependency_cache = {}
    dependency_cache.update(
        {
            Bot: bot,
            "bot": bot,
            "Bot": bot,
            Event: event,
            "event": event,
            "Event": event,
        }
    )
    dependency_cache.update(
        {
            StateT: state,
            "state": state,
        }
    )
    dependency_cache.update(
        {
            GlobalStateT: global_state,
            "global_state": global_state,
        }
    )
    dependency_cache.update(
        {
            NodeStateT: node_state,
            "node_state": node_state,
        }
    )
    if dependency_cache is not None:
        dependency_cache.update({DependencyCacheT: dependency_cache})
    return await solve_dependencies(
        dependent, use_cache=use_cache, stack=stack, dependency_cache=dependency_cache
    )
