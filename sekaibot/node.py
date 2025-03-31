"""SekaiBot 节点。

所有 SekaiBot 节点的基类。所有用户编写的节点必须继承自 `Node` 类。
"""

import inspect
from contextlib import AsyncExitStack
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,  # type: ignore
    Generic,
    NoReturn,
    Self,
    TypeVar,
    cast,
    final,
    get_args,
    get_origin,
)

import anyio
from exceptiongroup import BaseExceptionGroup, catch

from sekaibot.config import ConfigModel
from sekaibot.consts import JUMO_TO_TARGET, MAX_TIMEOUT, REJECT_TARGET
from sekaibot.dependencies import _T, Dependency, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import (
    FinishException,
    JumpToException,
    PruningException,
    RejectException,
    SkipException,
    StopException,
)
from sekaibot.internal.event import Event
from sekaibot.internal.message import BuildMessageType
from sekaibot.log import logger
from sekaibot.permission import Permission
from sekaibot.rule import Rule
from sekaibot.typing import (
    ConfigT,
    DependencyCacheT,
    EventT,
    GlobalStateT,
    NodeStateT,
    StateT,
)
from sekaibot.utils import flatten_exception_group, handle_exception, is_config_class

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Node", "Node", "NodeLoadType"]

NameT = TypeVar("NameT", bound="str")


class NodeLoadType(Enum):
    """节点加载类型。"""

    DIR = "dir"
    NAME = "name"
    FILE = "file"
    CLASS = "class"


class Node(Generic[EventT, NodeStateT, ConfigT]):
    """所有 SekaiBot 节点的基类。

    Attributes:
        parent: 节点的父节点名称。
        EventType: 节点处理的事件类型。
        Config: 节点的配置类。
        state: 节点的状态。
        bot: 节点所在的 Bot 实例。
        event: 当前正在被此节点处理的事件。
        priority: 节点的优先级，数字越小表示优先级越高，默认为 0。
        block: 节点执行结束后是否阻止事件的传播。`True` 表示阻止。
        load: 节点是否被加载，默认为 `True`，等同于使用以 `_` 开头的节点名。
        __node_load_type__: 节点加载类型，由 SekaiBot 自动设置，反映了此节点是如何被加载的。
        __node_file_path__: 当节点加载类型为 `NodeLoadType.CLASS` 时为 `None`，
            否则为定义节点在的 Python 模块的位置。
    """

    parent: ClassVar[str] = None
    priority: ClassVar[int] = 0
    block: ClassVar[bool] = False
    load: ClassVar[bool] = True

    __node_rule__: ClassVar[Rule] = Rule()
    __node_perm__: ClassVar[Permission] = Permission()

    __node_load_type__: ClassVar[NodeLoadType]
    __node_file_path__: ClassVar[str | None]

    # 不能使用 ClassVar 因为 PEP 526 不允许这样做
    EventType: str | type[Event] | tuple[type[Event]]
    Config: type[ConfigT]

    if TYPE_CHECKING:
        event: EventT
        state: StateT
        bot: "Bot"
    else:
        event = Depends(Event)
        bot = Depends("Bot")
        state = Depends(StateT)
        # 以下两个依赖项在节点作为依赖项时会被导入，并覆盖原有的 `name` 和 `config` 属性，应该交由 SekaiBot 处理
        # 由于依赖注入发生在类实例化时，因此 `Config` 不会被修改，但是 `config` 会被修改
        _name = Depends(NameT)
        _config = Depends(ConfigT)

    def __init_state__(self) -> NodeStateT | None:
        """初始化节点状态。"""

    def __init_subclass__(
        cls,
        event_type: type[EventT] | None = None,
        config: type[ConfigT] | None = None,
        init_state: NodeStateT | None = None,
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
            if not (inspect.isclass(origin_class) and issubclass(origin_class, Node)):
                continue
            try:
                event_t, state_t, config_t = cast(
                    tuple[EventT, NodeStateT, ConfigT], get_args(orig_base)
                )
            except ValueError:  # pragma: no cover
                continue
            if event_type is None:
                if inspect.isclass(event_t) and issubclass(event_t, Event):
                    event_type = event_t
                elif event_t:
                    _event_t = tuple(
                        filter(
                            lambda e: inspect.isclass(e) and issubclass(e, Event),
                            get_args(event_t),
                        )
                    )
                    event_type = (
                        _event_t[0]
                        if len(_event_t) == 1
                        else _event_t
                        if len(_event_t) > 0
                        else None
                    )
            if config is None and inspect.isclass(config_t) and issubclass(config_t, ConfigModel):
                config = config_t  # pyright: ignore
            if init_state is None:
                if get_origin(state_t) is Annotated and hasattr(state_t, "__metadata__"):
                    init_state = state_t.__metadata__[0]  # pyright: ignore
                elif inspect.isclass(state_t):
                    init_state = state_t()  # pyright: ignore
        if not hasattr(cls, "EventType") and event_type is not None:
            cls.EventType = event_type
        if not hasattr(cls, "Config") and config is not None:
            cls.Config = config
        if cls.__init_state__ is Node.__init_state__ and init_state is not None:
            cls.__init_state__ = lambda _: init_state  # type: ignore

        if cls.__name__.startswith("_"):
            cls.load = False

    @final
    @property
    def name(self) -> str:
        """节点类名称。"""
        return getattr(self, "_name", None) or self.__class__.__name__

    @final
    @property
    def config(self) -> ConfigT:
        """节点配置。"""
        default: Any = None
        config_class = getattr(self, "Config", None) or getattr(self, "_config", None)
        if is_config_class(config_class):
            _config = getattr(
                self.bot.config.node,
                config_class.__config_name__,
                default,
            )
            if isinstance(_config, dict):
                return config_class(**_config)
            return _config
        return default

    @property
    def node_state(self) -> NodeStateT:
        """节点状态。"""
        return self.bot.manager.node_state[self.name]

    @node_state.setter
    @final
    def node_state(self, value: NodeStateT) -> None:
        self.bot.manager.node_state[self.name] = value

    @property
    def global_state(self) -> dict:
        """通用状态。"""
        return self.bot.manager.global_state

    @global_state.setter
    @final
    def global_state(self, value: dict) -> None:
        self.bot.manager.global_state = value

    async def handle(self) -> None:
        """处理事件的方法。当 `rule()` 方法返回 `True` 时 SekaiBot 会调用此方法。每个节点必须实现此方法。"""

    async def rule(self) -> bool:
        """匹配事件的方法。事件处理时，会按照节点的优先级依次调用此方法，当此方法返回 `True` 时将事件交由此节点处理。每个节点不一定要实现此方法。
        注意：不建议直接在此方法内实现对事件的处理，事件的具体处理请交由 node 方法。
        """
        return True

    async def fallback(self) -> None:
        """事件不通过时执行的善后方法。当 `rule()` 方法返回 `False` 时 SekaiBot 会调用此方法。每个节点不一定要实现此方法。
        注意：此方法最好用于执行拒绝（`reject()`）等方法，不建议直接在此方法内实现对事件的处理，事件的具体处理请交由 node 方法。
        """

    async def reply(self, message: BuildMessageType) -> NoReturn:
        """回复消息。"""

    @final
    async def get(
        self,
        *,
        max_try_times: int | None = None,
        timeout: int | float = MAX_TIMEOUT,
    ) -> Self:
        """获取用户回复消息。

        相当于 `Bot` 的 `get()`，条件为适配器、事件类型、发送人相同。

        Args:
            max_try_times: 最大事件数。
            timeout: 超时时间。

        Returns:
            用户回复的消息事件。

        Raises:
            GetEventTimeout: 超过最大事件数或超时。
        """
        return await self.bot.manager.get(
            lambda e: e.get_session_id() == self.event.get_session_id(),
            event_type=type(self.event),
            max_try_times=max_try_times,
            timeout=timeout,
        )

    @final
    async def ask(
        self,
        message: str,
        max_try_times: int | None = None,
        timeout: int | float = MAX_TIMEOUT,
    ) -> Self:
        """询问消息。

        表示回复一个消息后获取用户的回复。
        相当于 `reply()` 后执行 `get()`。

        Args:
            message: 回复消息的内容。
            max_try_times: 最大事件数。
            timeout: 超时时间。

        Returns:
            用户回复的消息事件。
        """
        await self.reply(message)
        return await self.get(max_try_times=max_try_times, timeout=timeout)

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
        self.state[JUMO_TO_TARGET] = node
        raise JumpToException

    @final
    def prune(self) -> NoReturn:
        """中断事件的传播并将事件转发到下一个节点，即剪枝。"""
        raise PruningException

    @final
    def finish(self, message: BuildMessageType | None = None) -> NoReturn:
        """结束当前节点。"""
        if message:
            self.reply(message)
        raise FinishException

    @final
    def reject(
        self,
        message: BuildMessageType | None = None,
        max_try_times: int | None = None,
        timeout: int | float = MAX_TIMEOUT,
    ) -> NoReturn:
        if message:
            self.reply(message)
        self.state[REJECT_TARGET] = (max_try_times, timeout)
        raise RejectException

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
    @classmethod
    async def check_perm(
        cls,
        bot: "Bot",
        event: Event,
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """
        检查节点权限。
        """
        return (
            not hasattr(cls, "EventType")
            or (
                isinstance(cls.EventType, str)
                and (
                    event.type == (cls.EventType or event.type)
                    or event.get_event_name() == (cls.EventType or event.type)
                )
            )
            or (
                (
                    isinstance(cls.EventType, type)
                    and issubclass(cls.EventType, Event)
                    or isinstance(cls.EventType, tuple)
                    and all(issubclass(i, Event) for i in cls.EventType)
                )
                and isinstance(event, cls.EventType)
            )
        ) and await cls.__node_perm__(
            bot=bot,
            event=event,
            global_state=global_state,
            stack=stack,
            dependency_cache=dependency_cache,
        )

    @final
    @classmethod
    async def check_rule(
        cls,
        bot: "Bot",
        event: Event,
        state: StateT,
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """
        检查节点规则。
        """
        return await cls.__node_rule__(
            bot=bot,
            event=event,
            state=state,
            global_state=global_state,
            stack=stack,
            dependency_cache=dependency_cache,
        )

    @final
    async def _run_rule(self):
        """执行 rule() 方法并返回结果"""

        def _handle_special_exception(
            exc_group: BaseExceptionGroup[
                StopException
                | SkipException
                | JumpToException
                | PruningException
                | RejectException
                | FinishException
            ],
        ):
            mapping_dict = {
                StopException: "stop()",
                SkipException: "skip()",
                JumpToException: "jump_to()",
                PruningException: "prune()",
                RejectException: "reject()",
                FinishException: "finish()",
            }
            for exc in flatten_exception_group(exc_group):
                if exc in mapping_dict:
                    logger.warning(
                        f"You should not use `{mapping_dict[exc]}` in `rule()`, please instead use in node",
                        node=self.__class__,
                    )

        with catch(
            {
                (
                    StopException,
                    SkipException,
                    JumpToException,
                    PruningException,
                    RejectException,
                    FinishException,
                ): _handle_special_exception
            }
        ):
            return await self.rule()
        return False

    @final
    async def _run_handle(self):
        """执行 handle() 方法并返回结果

        Raise:
            BaseExceptionGroup[JumpToException | PruningException | RejectException]
        """

        def _handle_stop_exception(exc_group: BaseExceptionGroup[StopException]):
            logger.debug("Stopping exception caught in node", node=self.__class__)
            self.block = True

        with catch(
            {
                SkipException: handle_exception(
                    "Skip exception caught in node", level="debug", node=self.__class__
                ),
                FinishException: handle_exception(
                    "Finish exception caught in node", level="debug", node=self.__class__
                ),
                StopException: _handle_stop_exception,
            }
        ):
            await self.handle()

    @final
    async def _run_fallback(self):
        """执行 fallback() 方法并返回结果

        Raise:
            BaseExceptionGroup[JumpToException | RejectException]
        """

        def _handle_stop_exception(exc_group: BaseExceptionGroup[StopException]):
            logger.debug("Stopping exception caught in node", node=self.__class__)
            self.block = True

        with catch(
            {
                SkipException: handle_exception(
                    "Skip exception caught in node", level="debug", node=self.__class__
                ),
                FinishException: handle_exception(
                    "Finish exception caught in node", level="debug", node=self.__class__
                ),
                PruningException: handle_exception(
                    "Pruning exception caught in node", level="debug", node=self.__class__
                ),
                StopException: _handle_stop_exception,
            }
        ):
            await self.fallback()

    @final
    async def _run_node(self) -> PruningException | JumpToException | None:
        """执行 node 并返回结果

        Return:
            PruningException | JumpToException | None
        Raise:
            StopException | Any
        """
        exc: RejectException | JumpToException | PruningException | None = None

        def _handle_special_exception(
            exc_group: BaseExceptionGroup[RejectException | JumpToException | PruningException],
        ):
            nonlocal exc
            excs = list(flatten_exception_group(exc_group))
            if len(excs) > 1:
                logger.warning(
                    "Multiple session control exceptions occurred. "
                    "SekaiBot will choose the proper one."
                )
                reject = next(
                    (e for e in excs if isinstance(e, RejectException)),
                    None,
                )
                jumpto_exc = next(
                    (e for e in excs if isinstance(e, JumpToException)),
                    None,
                )
                pruning_exc = next(
                    (e for e in excs if isinstance(e, PruningException)),
                    None,
                )
                exc = reject or jumpto_exc or pruning_exc
            elif isinstance(excs[0], PruningException | JumpToException | RejectException):
                exc = excs[0]

        rule_failed = True

        with catch(
            {(PruningException, JumpToException, RejectException): _handle_special_exception}
        ):
            if await self._run_rule():
                logger.info("Event will be handled by node", node=self.__class__)
                rule_failed = False
                await self._run_handle()
            else:
                await self._run_fallback()
        if exc:
            if isinstance(exc, RejectException):
                if self.state[REJECT_TARGET]:
                    max_try_times, timeout = self.state[REJECT_TARGET]
                    logger.debug("Rejecting exception caught in node", node=self.__class__)
                    await self.bot.manager._add_temporary_task(
                        self.__class__, self.event, self.state, max_try_times, timeout
                    )
                else:
                    logger.warning(
                        "Rejecting exception caught in node but it does not have the target",
                        node=self.__class__,
                    )
                exc = None
            elif isinstance(exc, JumpToException):
                if self.block:
                    logger.warning(
                        "should not use `jump_to()` when block is `true`", node=self.__class__
                    )
                    exc = None
                logger.debug("JumpTo exception caught in node", node=self.__class__)
            elif isinstance(exc, PruningException):
                if self.block:
                    logger.warning(
                        "should not use `prune()` when block is `true`", node=self.__class__
                    )
                    exc = None
                logger.debug("Pruning exception caught in node", node=self.__class__)
        if rule_failed:
            exc = PruningException()
        if self.block:
            raise StopException

        return exc

    @final
    async def run(
        self,
        dependent: Dependency[_T],
    ) -> _T:
        """在节点内运行 SekaiBot 内置的，或自定义的函数，以及具有 `__call__` 的类。
        这些函数只能含有 Bot, Event, State 三个参数。
        """
        result: _T = ...
        async with AsyncExitStack() as stack:
            result = await solve_dependencies_in_bot(
                dependent,
                bot=self.bot,
                event=self.event,
                state=self.state,
                node_state=self.node_state,
                global_state=self.bot.manager.global_state,
                stack=stack,
            )
        return result

    @final
    async def gather(
        self, *dependencies: Dependency[_T], return_exceptions: bool = False
    ) -> tuple[_T, ...]:
        """类似 `asyncio.gather()` 并发执行多个任务，支持 `return_exceptions`"""

        results = {}

        async def wrapper(dep):
            nonlocal results
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
