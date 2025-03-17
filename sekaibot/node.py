"""SekaiBot 节点。

所有 SekaiBot 节点的基类。所有用户编写的节点必须继承自 `Node` 类。
"""

import inspect
import anyio
from abc import ABC, abstractmethod
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    List,
    ClassVar,
    Self,
    Generic,
    NoReturn,
    Optional,
    Callable,
    Awaitable,
    Tuple,
    Type,
    cast,
    final,
) # type: ignore
from typing_extensions import Annotated, get_args, get_origin
from contextlib import AsyncExitStack

from sekaibot.consts import NODE_STATE, NODE_GLOBAL_STATE
from sekaibot.config import ConfigModel
from sekaibot.dependencies import Depends, Dependency, solve_dependencies_in_bot, _T
from sekaibot.internal.event import Event
from sekaibot.exceptions import SkipException, JumpToException, PruningException, StopException
from sekaibot.typing import ConfigT, EventT, StateT
from sekaibot.utils import is_config_class
from sekaibot.rule import Rule
from sekaibot.permission import Permission

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Node", "NodeLoadType"]


class NodeLoadType(Enum):
    """节点加载类型。"""

    DIR = "dir"
    NAME = "name"
    FILE = "file"
    CLASS = "class"


class Node(ABC, Generic[EventT, StateT, ConfigT]):
    """所有 SekaiBot 节点的基类。

    Attributes:
        event: 当前正在被此节点处理的事件。
        priority: 节点的优先级，数字越小表示优先级越高，默认为 0。
        block: 节点执行结束后是否阻止事件的传播。`True` 表示阻止。
        __node_load_type__: 节点加载类型，由 SekaiBot 自动设置，反映了此节点是如何被加载的。
        __node_file_path__: 当节点加载类型为 `NodeLoadType.CLASS` 时为 `None`，
            否则为定义节点在的 Python 模块的位置。
    """

    parent: ClassVar[str] = None
    priority: ClassVar[int] = 0
    sand_box: ClassVar[bool] = False
    block: ClassVar[bool] = False

    # 不能使用 ClassVar 因为 PEP 526 不允许这样做
    EventType: str | type[Event] | tuple[type[Event]]
    Config: type[ConfigT]

    __node_rule__: ClassVar[Rule] = Rule()
    __node_perm__: ClassVar[Permission] = Permission()

    __node_load_type__: ClassVar[NodeLoadType]
    __node_file_path__: ClassVar[Optional[str]]

    if TYPE_CHECKING:
        event: EventT
        bot: "Bot"
    else:
        event = Depends(Event)
        bot = Depends("Bot")


    def __init_state__(self) -> Optional[StateT]:
        """初始化节点状态。"""

    def __init_subclass__(
        cls,
        event_type: Optional[type[EventT]] = None,
        config: Optional[type[ConfigT]] = None,
        init_state: Optional[StateT] = None,
        **_kwargs: Any,
    ) -> None:
        """初始化子类。

        Args:
            event_type: 事件类型。
            config: 配置类。
            init_state: 初始状态。
        """
        super().__init_subclass__()

        orig_bases: tuple[type, ...] = getattr(cls, "__orig_bases__", ())
        for orig_base in orig_bases:
            origin_class = get_origin(orig_base)
            if inspect.isclass(origin_class) and issubclass(origin_class, Node):
                try:
                    event_t, state_t, config_t = cast(
                        tuple[EventT, StateT, ConfigT], get_args(orig_base)
                    )
                except ValueError:  # pragma: no cover
                    continue
                if event_type is None:
                    if (
                        inspect.isclass(event_t)
                        and issubclass(event_t, Event)
                    ):
                        event_type = event_t
                    else:
                        _event_t = tuple(filter(lambda e: inspect.isclass(e) and issubclass(e, Event), get_args(event_t)))
                        event_type = _event_t[0] if len(_event_t) == 1 else _event_t if len(_event_t) >0 else None
                if (
                    config is None
                    and inspect.isclass(config_t)
                    and issubclass(config_t, ConfigModel)
                ):
                    config = config_t  # pyright: ignore
                if (
                    init_state is None
                    and get_origin(state_t) is Annotated
                    and hasattr(state_t, "__metadata__")
                ):
                    init_state = state_t.__metadata__[0]  # pyright: ignore

        if not hasattr(cls, "EventType") and event_type is None:
            cls.EventType = event_type
        if not hasattr(cls, "Config") and config is not None:
            cls.Config = config
        if cls.__init_state__ is Node.__init_state__ and init_state is not None:
            cls.__init_state__ = lambda _: init_state  # type: ignore

    @final
    @property
    def name(self) -> str:
        """节点类名称。"""
        return self.__class__.__name__
    
    async def run(
        self,
        dependent: Dependency[_T],
    ) -> _T:
        """在节点内运行 SekaiBot 内置的，或自定义的函数，以及具有 `__call__` 的类。
            这些函数只能含有 Bot, Event, State 三个参数。
        """
        return await solve_dependencies_in_bot(
            dependent,
            bot=self.bot,
            event=self.event,
            state=self.bot.manager.node_state,
            stack=AsyncExitStack()
        )
    
    async def gather(
        self,
        *dependencies: Dependency[_T],
        return_exceptions: bool = False
    ) -> tuple[_T, ...]:
        """类似 `asyncio.gather()` 并发执行多个任务，支持 `return_exceptions`"""

        results = {}

        async def wrapper(dep):
            try:
                results[dep] = await self.run(dep)
            except Exception as e:
                if return_exceptions:
                    results[dep] = e 
                else:
                    raise 

        async with anyio.create_task_group() as tg:
            for dependency in dependencies:
                tg.start_soon(wrapper, dependency)

        return tuple(results[dep] for dep in dependencies)

    
    '''async def call_api(self, api: str, **params: Any):
        """调用 API，协程会等待直到获得 API 响应。

        Args:
            api: API 名称。
            **params: API 参数。

        Returns:
            API 响应中的 data 字段。

        Raises:
            NetworkError: 网络错误。
            ApiNotAvailable: API 请求响应 404， API 不可用。
            ActionFailed: API 请求响应 failed， API 操作失败。
            ApiTimeout: API 请求响应超时。
        """
        return await self.comm.adapter.call_api(api, **params)'''

    @final
    @property
    def config(self) -> ConfigT:
        """节点配置。"""
        default: Any = None
        config_class = getattr(self, "Config", None)
        if is_config_class(config_class):
            return getattr(
                self.bot.config.node,
                config_class.__config_name__,
                default,
            )
        return default

    @property
    def state(self) -> StateT:
        """节点状态。"""
        return self.bot.manager.node_state[self.name][NODE_STATE]

    @state.setter
    @final
    def state(self, value: StateT) -> None:
        self.bot.manager.node_state[self.name][NODE_STATE] = value

    @property
    def global_state(self) -> dict:
        """通用状态。"""
        return self.bot.manager.global_state[NODE_GLOBAL_STATE]

    @global_state.setter
    @final
    def global_state(self, value: dict) -> None:
        self.bot.manager.global_state[NODE_GLOBAL_STATE] = value

    @final
    @classmethod
    async def check_perm(
        cls,
        bot: Bot,
        event: Event,
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[Dependency] = None,
    ) -> bool:
        return (
            isinstance(cls.EventType, str) and event.type == (cls.EventType or event.type)
            or isinstance(event, cls.EventType)
        ) and await cls.__node_perm__(
            bot=bot, event=event,
            stack=stack,
            dependency_cache=dependency_cache,
        )

    @final
    @classmethod
    async def check_rule(
        cls,
        bot: Bot,
        event: Event,
        state: StateT,
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[Dependency] = None,
    ) -> bool:
        return (
            isinstance(cls.EventType, str) and event.type == (cls.EventType or event.type)
            or isinstance(event, cls.EventType)
        ) and await cls.__node_rule__(
            bot=bot, event=event, state=state,
            stack=stack,
            dependency_cache=dependency_cache,
        )

    @abstractmethod
    async def handle(self) -> None:
        """处理事件的方法。当 `rule()` 方法返回 `True` 时 SekaiBot 会调用此方法。每个节点必须实现此方法。"""
        raise NotImplementedError

    async def rule(self) -> bool:
        """匹配事件的方法。事件处理时，会按照节点的优先级依次调用此方法，当此方法返回 `True` 时将事件交由此节点处理。每个节点不一定要实现此方法。

        注意：不建议直接在此方法内实现对事件的处理，事件的具体处理请交由 `handle()` 方法。
        """
        return True
    
    @final
    def stop(self) -> NoReturn:
        """停止当前事件传播。"""
        raise StopException

    @final
    def skip(self) -> NoReturn:
        """跳过自身继续当前事件传播。"""
        raise SkipException
    
    @final
    def jump_to(self, node: str) -> NoReturn:
        """跳过自身并将事件转发到下一个节点。"""
        raise JumpToException(node)
    
    @final
    def prune(self) -> NoReturn:
        """中断事件的传播并将事件转发到下一个节点，即剪枝。"""
        raise PruningException
