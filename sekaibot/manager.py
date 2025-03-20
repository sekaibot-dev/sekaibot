import asyncio
import time
from contextlib import AsyncExitStack
from exceptiongroup import BaseExceptionGroup, catch
from collections import defaultdict
import anyio
from anyio.abc import TaskStatus
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    overload,
)

from sekaibot.exceptions import (
    GetEventTimeout,
    StopException,
    SkipException,
    PruningException,
    JumpToException,
    RejectException,
)
from sekaibot.consts import MAX_TIMEOUT
from sekaibot.log import logger
from sekaibot.typing import EventT, NodeStateT, StateT
from sekaibot.node import Node
from sekaibot.utils import wrap_get_func, cancel_on_exit, flatten_exception_group, handle_exception
from sekaibot.dependencies import solve_dependencies_in_bot, Dependency
from sekaibot.internal.event import Event, EventHandleOption

if TYPE_CHECKING:
    from sekaibot.bot import Bot

class NodeManager():
    bot: "Bot"

    node_state: dict[str, Any]
    global_state: dict[str, Any]

    _condition: anyio.Condition
    _cancel_event: anyio.Event
    _current_event: Event | None

    _event_send_stream: MemoryObjectSendStream[EventHandleOption]  # pyright: ignore[reportUninitializedInstanceVariable]
    _event_receive_stream: MemoryObjectReceiveStream[EventHandleOption]  # pyright: ignore[reportUninitializedInstanceVariable]

    def __init__(self, bot: "Bot"):
        self.bot = bot
        self.node_state = defaultdict(lambda: None)
        self.global_state = defaultdict(dict)

    async def startup(self) -> None:
        self._condition = anyio.Condition()
        self._cancel_event = anyio.Event()
        self._event_send_stream, self._event_receive_stream = (
            anyio.create_memory_object_stream(
                max_buffer_size=self.bot.config.bot.event_queue_size
            )
        )

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._handle_event_receive)
            tg.start_soon(cancel_on_exit, self._cancel_event, tg)

    async def handle_event(
        self,
        current_event: Event[Any],
        *,
        handle_get: bool = True,
        show_log: bool = True,
    ) -> None:
        """被适配器对象调用，根据优先级分发事件给所有插件，并处理插件的 `stop` 、 `skip` 等信号。

        此方法不应该被用户手动调用。

        Args:
            current_event: 当前待处理的 `Event`。
            handle_get: 当前事件是否可以被 get 方法捕获，默认为 `True`。
            show_log: 是否在日志中显示，默认为 `True`。
        """
        if show_log:
            logger.info(
                "Event received from adapter",
                current_event=current_event,
            )

        await self._event_send_stream.send(
            EventHandleOption(
                event=current_event,
                handle_get=handle_get,
            )
        )

    async def _handle_event_receive(self) -> None:
        async with anyio.create_task_group() as tg, self._event_receive_stream:
            async for current_event, handle_get in self._event_receive_stream:
                if handle_get:
                    await tg.start(self._handle_event_wait_condition)
                    async with self._condition:
                        self._current_event = current_event
                        self._condition.notify_all()
                else:
                    tg.start_soon(self._handle_event, current_event)

    async def _handle_event_wait_condition(
        self, *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED
    ) -> None:
        async with self._condition:
            task_status.started()
            await self._condition.wait()
            assert self._current_event is not None
            current_event = self._current_event
        await self._handle_event(current_event)

    async def _add_temporary_task(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
        max_try_times: int | None = None,
        timeout: int | float = MAX_TIMEOUT,
    ):
        """添加一个临时节点任务，在调用 reject 时运行。

        Args:
            node: 要添加的节点，必须是类实例。
            max_try_times: 最大事件数。
            timeout: 超时时间。
        """

        async def temporary_task(func: Callable[[Event], bool | Awaitable[bool]] | None = None):
            event_copy: Event[Any] | None = None
            async def check(event: Event[Any]) -> bool:
                if event.get_session_id() != current_event.get_session_id(): return False
                return await wrap_get_func(func)(event)
            try:
                event = await self.get(
                    check,
                    event_type=type(current_event),
                    max_try_times=max_try_times,
                    timeout=timeout,
                )
                event_copy = event.model_copy()
                await self._check_and_run(node_class, event, state)
            except GetEventTimeout:
                return
            except RejectException as reject:
                if event_copy:
                    # 将事件重新放回时间传播
                    event_copy.__handled__ = False
                    await self._add_temporary_task(node_class, current_event, state, reject.max_try_times, reject.timeout)
                    await self.handle_event(event_copy, show_log=False)

            except Exception:
                logger.exception("Exception in node", node=node_class)

        async with anyio.create_task_group() as tg:
            tg.start_soon(temporary_task)

    async def _check_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: Dependency | None = None,
    ) -> bool:
        """检查事件响应器是否符合运行条件。

        请注意，过时的事件响应器将被**销毁**。对于未过时的事件响应器，将会一次检查其响应类型、权限和规则。

        参数:
            Matcher: 要检查的事件响应器
            bot: Bot 对象
            event: Event 对象
            state: 会话状态
            stack: 异步上下文栈
            dependency_cache: 依赖缓存

        返回:
            bool: 是否符合运行条件
        """

        try:
            if not await node_class.check_perm(self.bot, current_event, self.global_state, stack, dependency_cache):
                logger.info(f"permission conditions not met", node=node_class.__name__)
                return False
        except Exception:
            logger.exception(
                f"permission check failed", node=node_class.__name__
            )
            return False

        try:
            if not await node_class.check_rule(self.bot, current_event, state, stack, dependency_cache):
                logger.info(f"rule conditions not met", node=node_class.__name__)
                return False
        except Exception:
            logger.exception(
                f"rule check failed", node=node_class.__name__
            )
            return False

        return True

    async def _run_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: Dependency | None = None,
    ):
        _node = await solve_dependencies_in_bot(
            node_class,
            bot=self.bot, 
            event=current_event,
            state=state, 
            node_state=self.node_state[node_class.__name__], 
            global_state=self.global_state,
            use_cache=True,
            stack=stack,
            dependency_cache=dependency_cache,
        )

        if _node.name not in self.node_state:
            state = _node.__init_state__()
            if state is not None:
                self.node_state[_node.name] = state


        if not await _node._run_rule():
            await _node._run_fallback()
            raise PruningException
        logger.info("Event will be handled by node", node=_node)
        await _node._run_handle()
                
    async def _check_and_run_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
    ):
        async with AsyncExitStack() as stack:
            if not await self._check_node(node_class, current_event, state, stack=stack):
                raise PruningException

            await self._run_node(node_class, current_event, state, stack=stack)

    async def _simple_run_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
    ) -> RejectException | PruningException | JumpToException | None:
        """运行节点并处理特殊异常。"""
        exc: RejectException | PruningException | JumpToException | None = (
            None
        )

        def _handle_special_exception(
            exc_group: BaseExceptionGroup[
                RejectException | PruningException | JumpToException
            ],
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
                pruning_exc = next(
                    (e for e in excs if isinstance(e, PruningException)),
                    None,
                )
                jumpto_exc = next(
                    (e for e in excs if isinstance(e, JumpToException)),
                    None,
                )
                exc = reject or pruning_exc or jumpto_exc
            elif isinstance(
                excs[0], (PruningException, JumpToException, RejectException)
            ):
                exc = excs[0]
        
        with catch(
            {
                (
                    PruningException, 
                    JumpToException, 
                    RejectException
                ): _handle_special_exception
            }
        ):
            await self._check_and_run_node(node_class, current_event, state)

        return exc
        
    async def _handle_event(self, current_event: Event[Any]) -> None:
        """处理事件并匹配相应的节点（插件）。

        此方法在 `current_event` 被处理后不会再次处理，遍历 `nodes_list`
        来匹配事件，并根据插件的处理结果进行剪枝、跳转或停止。

        Args:
            current_event: 当前需要处理的事件对象。
        """
        if current_event.__handled__:
            return

        for hook_func in self.bot._event_preprocessor_hooks:
            await hook_func(current_event)

        nodes_list = self.bot.nodes_list.copy()
        index = 0
        jump_to_index_map = {node.__name__: i for i, (node, _) in enumerate(nodes_list)}

        while index < len(nodes_list):
            node_class, pruning_node = nodes_list[index]
            state = defaultdict(lambda: None)

            logger.debug("Checking for matching nodes", priority=node_class)

            next_index = index + 1

            exc = await self._simple_run_node(node_class, current_event, state)

            if isinstance(exc, PruningException):
                logger.debug("Pruning exception caught in node", node=node_class)
                if pruning_node == -1:
                    break
                next_index = pruning_node

            elif isinstance(exc, JumpToException):
                jump_to_index = jump_to_index_map.get(exc.node)

                if jump_to_index is None:
                    logger.warning("The node to jump to does not exist", node_name=exc.node)
                    continue  # 继续下一个节点
                elif jump_to_index > index:
                    logger.debug("Jumping exception caught in node", node=nodes_list[jump_to_index])
                    next_index = jump_to_index
                else:
                    logger.warning("The node to jump to is before the current node", node=nodes_list[jump_to_index])

            elif isinstance(exc, RejectException):
                logger.debug("Rejecting exception caught in node", node=node_class)
                await self._add_temporary_task(node_class, current_event, state, exc.max_try_times, exc.timeout)

            if node_class.block:
                break

            index = next_index

        for hook_func in self.bot._event_postprocessor_hooks:
            await hook_func(current_event)

        logger.info("Event Finished")

    async def shutdown(self) -> None:
        """关闭并清理事件。"""
        self._cancel_event.set()
        self.node_state.clear()

    @overload
    async def get(
        self,
        func: Callable[[Event], bool | Awaitable[bool]] | None = None,
        *,
        event_type: None = None,
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> Event: ...

    @overload
    async def get(
        self,
        func: Callable[[EventT], bool | Awaitable[bool]] | None = None,
        *,
        event_type: None = None,
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> EventT: ...

    @overload
    async def get(
        self,
        func: Callable[[EventT], bool | Awaitable[bool]] | None = None,
        *,
        event_type: type[EventT],
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> EventT: ...

    async def get(
        self,
        func: Callable[[Any], bool | Awaitable[bool]] | None = None,
        *,
        event_type: type[Event] | None = None,
        max_try_times: int | None = None,
        timeout: int | float = MAX_TIMEOUT,
    ) -> EventT:
        """获取满足指定条件的的事件，协程会等待直到适配器接收到满足条件的事件、超过最大事件数或超时。

        Args:
            func: 协程或者函数，函数会被自动包装为协程执行。
                要求接受一个事件作为参数，返回布尔值。当协程返回 `True` 时返回当前事件。
                当为 `None` 时相当于输入对于任何事件均返回真的协程，即返回适配器接收到的下一个事件。
            event_type: 当指定时，只接受指定类型的事件，先于 func 条件生效。默认为 `None`。
            adapter_type: 当指定时，只接受指定适配器产生的事件，先于 func 条件生效。默认为 `None`。
            max_try_times: 最大事件数。
            timeout: 超时时间。

        Returns:
            返回满足 `func` 条件的事件。

        Raises:
            GetEventTimeout: 超过最大事件数或超时。
        """
        _func = wrap_get_func(func)

        try_times = 0
        start_time = time.time()
        while not self.bot._should_exit.is_set():
            if max_try_times is not None and try_times > max_try_times:
                break
            if timeout is not None and time.time() - start_time > timeout:
                break

            async with self._condition:
                if timeout is None:
                    await self._condition.wait()
                else:
                    try:
                        await asyncio.wait_for(
                            self._condition.wait(),
                            timeout=start_time + timeout - time.time(),
                        )
                    except asyncio.TimeoutError:
                        break

                if (
                    self._current_event is not None
                    and not self._current_event.__handled__
                    and (
                        event_type is None
                        or isinstance(self._current_event, event_type)
                    )
                    and await _func(self._current_event)
                ):
                    self._current_event.__handled__ = True
                    logger.debug("Event caught", event=self._current_event)
                    return self._current_event

                try_times += 1

        raise GetEventTimeout
