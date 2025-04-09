import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, overload

import anyio
from anyio.abc import TaskStatus
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from exceptiongroup import BaseExceptionGroup, catch

from sekaibot.consts import JUMO_TO_TARGET, MAX_TIMEOUT
from sekaibot.dependencies import solve_dependencies_in_bot
from sekaibot.exceptions import (
    GetEventTimeout,
    IgnoreException,
    JumpToException,
    PruningException,
    SkipException,
    StopException,
)
from sekaibot.internal.adapter import Adapter
from sekaibot.internal.event import Event, EventHandleOption
from sekaibot.internal.node import NameT, Node
from sekaibot.log import logger
from sekaibot.typing import ConfigT, DependencyCacheT, EventT, StateT
from sekaibot.utils import cancel_on_exit, handle_exception, run_coro_with_catch, wrap_get_func

if TYPE_CHECKING:
    from sekaibot.bot import Bot


class NodeManager:
    bot: "Bot"

    _condition: anyio.Condition
    _cancel_event: anyio.Event
    _current_event: Event[Adapter[Any, Any]] | None

    _event_send_stream: MemoryObjectSendStream[EventHandleOption]  # pyright: ignore[reportUninitializedInstanceVariable]
    _event_receive_stream: MemoryObjectReceiveStream[EventHandleOption]  # pyright: ignore[reportUninitializedInstanceVariable]

    def __init__(self, bot: "Bot"):
        self.bot = bot

    async def startup(self) -> None:
        self._condition = anyio.Condition()
        self._cancel_event = anyio.Event()
        self._event_send_stream, self._event_receive_stream = anyio.create_memory_object_stream(
            max_buffer_size=self.bot.config.bot.event_queue_size
        )

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._handle_event_receive)
            tg.start_soon(cancel_on_exit, self._cancel_event, tg)

    async def _run_event_preprocessors(
        self,
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """运行事件预处理。

        参数:
            current_event: Event[Any] 对象
            state: 会话状态
            stack: 异步上下文栈
            dependency_cache: 依赖缓存

        返回:
            是否继续处理事件
        """
        if not self.bot._event_preprocessor_hooks:
            return True

        logger.debug("Running PreProcessors...")

        with catch(
            {
                IgnoreException: handle_exception(
                    "Event is ignored", level="info", name=current_event.get_event_name()
                ),
                Exception: handle_exception(
                    "Error when running EventPreProcessors. Event ignored!"
                ),
            }
        ):
            async with anyio.create_task_group() as tg:
                for hook_func in self.bot._event_preprocessor_hooks:
                    tg.start_soon(
                        run_coro_with_catch,
                        solve_dependencies_in_bot(
                            hook_func,
                            bot=self.bot,
                            event=current_event,
                            state=state,
                            stack=stack,
                            dependency_cache=dependency_cache,
                        ),
                        (SkipException,),
                    )

            return True

        return False

    async def _run_event_postprocessors(
        self,
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> None:
        """运行事件后处理。

        参数:
            current_event: Event[Any] 对象
            state: 会话状态
            stack: 异步上下文栈
            dependency_cache: 依赖缓存
        """
        if not self.bot._event_postprocessor_hooks:
            return

        logger.debug("Running PostProcessors...")

        with catch({Exception: handle_exception("Error when running EventPostProcessors")}):
            async with anyio.create_task_group() as tg:
                for hook_func in self.bot._event_postprocessor_hooks:
                    tg.start_soon(
                        run_coro_with_catch,
                        solve_dependencies_in_bot(
                            hook_func,
                            bot=self.bot,
                            event=current_event,
                            state=state,
                            stack=stack,
                            dependency_cache=dependency_cache,
                        ),
                        (SkipException,),
                    )

    async def _run_node_preprocessors(
        self,
        current_event: Event[Any],
        state: StateT,
        node: Node,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """运行事件响应器运行前处理。

        参数:
            bot: Bot 对象
            current_event: Event[Any] 对象
            state: 会话状态
            matcher: 事件响应器
            stack: 异步上下文栈
            dependency_cache: 依赖缓存

        返回:
            是否继续处理事件
        """
        if not self.bot._node_preprocessor_hooks:
            return True

        with (
            catch(
                {
                    IgnoreException: handle_exception(
                        "running is cancelled", level="info", node=node.name
                    ),
                    Exception: handle_exception(
                        "Error when running RunPreProcessors. Running cancelled!"
                    ),
                }
            ),
        ):
            async with anyio.create_task_group() as tg:
                for hook_func in self.bot._node_preprocessor_hooks:
                    tg.start_soon(
                        run_coro_with_catch,
                        solve_dependencies_in_bot(
                            hook_func,
                            node=node,
                            bot=self.bot,
                            event=current_event,
                            state=state,
                            stack=stack,
                            dependency_cache=dependency_cache,
                        ),
                        (SkipException,),
                    )

            return True

        return False

    async def _run_node_postprocessors(
        self,
        current_event: "Event",
        node: Node,
        exception: Exception | None = None,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> None:
        """运行事件响应器运行后处理。

        参数:
            bot: Bot 对象
            current_event: Event[Any] 对象
            matcher: 事件响应器
            exception: 事件响应器运行异常
            stack: 异步上下文栈
            dependency_cache: 依赖缓存
        """
        if not self.bot._node_postprocessor_hooks:
            return

        with (
            catch({Exception: handle_exception("Error when running RunPostProcessors. ")}),
        ):
            async with anyio.create_task_group() as tg:
                for hook_func in self.bot._node_postprocessor_hooks:
                    tg.start_soon(
                        run_coro_with_catch,
                        solve_dependencies_in_bot(
                            hook_func,
                            node=node,
                            exception=exception,
                            bot=self.bot,
                            event=current_event,
                            state=node.state,
                            stack=stack,
                            dependency_cache=dependency_cache,
                        ),
                        (SkipException,),
                    )

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
                await current_event.adapter.event_preprocess(current_event)
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
            async def check(event: Event[Any]) -> bool:
                if event.get_session_id() != current_event.get_session_id():
                    return False
                return await wrap_get_func(func)(event)

            try:
                event = await self.get(
                    check,
                    event_type=type(current_event),
                    max_try_times=max_try_times,
                    timeout=timeout,
                )
                event_copy = event.model_copy()
                event_copy.__handled__ = False
                await self._handle_event(event_copy, state, node_class)
            except GetEventTimeout:
                return

        async with anyio.create_task_group() as tg:
            tg.start_soon(temporary_task)

    async def _check_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """检查事件响应器是否符合运行条件。

        请注意，过时的事件响应器将被**销毁**。对于未过时的事件响应器，将会一次检查其响应类型、权限和规则。

        参数:
            Matcher: 要检查的事件响应器
            bot: Bot 对象
            current_event: Event[Any] 对象
            state: 会话状态
            stack: 异步上下文栈
            dependency_cache: 依赖缓存

        返回:
            bool: 是否符合运行条件
        """

        try:
            if not await node_class._check_perm(
                self.bot, current_event, self.bot.global_state, stack, dependency_cache
            ):
                logger.debug("permission conditions not met", node=node_class.__name__)
                return False
        except Exception:
            logger.exception("permission check failed", node=node_class.__name__)
            return False

        try:
            if not await node_class._check_rule(
                self.bot, current_event, state, self.bot.global_state, stack, dependency_cache
            ):
                logger.debug("rule conditions not met", node=node_class.__name__)
                return False
        except Exception:
            logger.exception("rule check failed", node=node_class.__name__)
            return False

        return True

    async def _run_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> tuple[PruningException | JumpToException | None, StateT]:

        _node = await solve_dependencies_in_bot(
            node_class,
            bot=self.bot,
            event=current_event,
            state=state,
            node_state=self.bot.node_state.get(node_class.__name__),
            global_state=self.bot.global_state,
            use_cache=True,
            stack=stack,
            dependency_cache=dependency_cache,
        )

        if _node.name not in self.bot.node_state:
            state = _node.__init_state__()
            if state is not None:
                self.bot.node_state[_node.name] = state

        if not await self._run_node_preprocessors(
            current_event=current_event,
            state=state,
            node=_node,
            stack=stack,
            dependency_cache=dependency_cache,
        ):
            return None, None

        exception = await _node._run_node()

        await self._run_node_postprocessors(
            current_event=current_event,
            node=_node,
            exception=exception,
            stack=stack,
            dependency_cache=dependency_cache,
        )
        return exception, _node.state

    async def _check_and_run_node(
        self,
        node_class: type[Node],
        current_event: Event[Any],
        state: StateT,
        stack: AsyncExitStack | None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> tuple[PruningException | JumpToException | None, StateT | None]:
        if not await self._check_node(node_class, current_event, state, stack, dependency_cache):
            return PruningException(), None

        return await self._run_node(node_class, current_event, state, stack, dependency_cache)

    async def _handle_event(
        self,
        current_event: Event[Any],
        state: StateT | None = None,
        start_class: type[Node[Any, Any, Any]] | None = None,
    ) -> None:
        """处理事件并匹配相应的节点（插件）。

        此方法在 `current_event` 被处理后不会再次处理，遍历 `nodes_list`
        来匹配事件，并根据插件的处理结果进行剪枝、跳转或停止。

        Args:
            current_event: 当前需要处理的事件对象。
        """
        if current_event.__handled__:
            return

        async with AsyncExitStack() as stack:
            dependency_cache = {}

            if not await self._run_event_preprocessors(
                current_event=current_event,
                state=state,
                stack=stack,
                dependency_cache=dependency_cache,
            ):
                return

            nodes_list = self.bot.nodes_list.copy()
            state = state or defaultdict(lambda: None)
            jump_to_index_map = {node.__name__: i for i, (node, _) in enumerate(nodes_list)}
            index = jump_to_index_map.get(start_class.__name__, 0) if start_class else 0
            interrupted = False

            def _handle_stop_propagation(exc_group: BaseExceptionGroup) -> None:
                nonlocal interrupted
                interrupted = True
                logger.debug("Stop event propagation")

            while index < len(nodes_list) and not interrupted:
                node_class, pruning_node = nodes_list[index]

                logger.debug("Checking for matching nodes", priority=node_class)

                next_index = index + 1

                with catch(
                    {
                        StopException: _handle_stop_propagation,
                        Exception: handle_exception("Error when running Node.", node=node_class),
                    }
                ):
                    exc, _state = await self._check_and_run_node(
                        node_class,
                        current_event,
                        state.copy(),
                        stack,
                        dependency_cache
                        | {
                            NameT: node_class.__name__,
                            ConfigT: getattr(node_class, "Config", None),
                        },
                    )

                    if isinstance(exc, PruningException):
                        if pruning_node == -1:
                            break
                        next_index = pruning_node

                    elif isinstance(exc, JumpToException):
                        if node_name := _state[JUMO_TO_TARGET]:
                            jump_to_index = jump_to_index_map.get(node_name)
                            if jump_to_index is None:
                                logger.warning(
                                    "The node to jump to does not exist",
                                    node_name=node_name,
                                )
                            elif jump_to_index > index:
                                next_index = jump_to_index
                            else:
                                logger.warning(
                                    "The node to jump to is before the current node",
                                    node=nodes_list[jump_to_index],
                                )
                        else:
                            logger.warning(
                                "Rejecting exception caught in node but it does not have the target",
                                node=node_class,
                            )

                index = next_index

            logger.debug("Checking for nodes completed")

            await self._run_event_postprocessors(
                current_event=current_event,
                state=state,
                stack=stack,
                dependency_cache=dependency_cache,
            )

        logger.info("Event Finished")

    async def shutdown(self) -> None:
        """关闭并清理事件。"""
        self._cancel_event.set()
        self.bot.node_state.clear()

    @overload
    async def get(
        self,
        func: Callable[[Event[Any]], bool | Awaitable[bool]] | None = None,
        *,
        event_type: None = None,
        adapter_type: None = None,
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> Event[Any]: ...

    @overload
    async def get(
        self,
        func: Callable[[EventT], bool | Awaitable[bool]] | None = None,
        *,
        event_type: None = None,
        adapter_type: type[Adapter[EventT, Any]],
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> EventT: ...

    @overload
    async def get(
        self,
        func: Callable[[EventT], bool | Awaitable[bool]] | None = None,
        *,
        event_type: type[EventT],
        adapter_type: type[Adapter[Any, Any]] | None = None,
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> EventT: ...

    async def get(
        self,
        func: Callable[[Any], bool | Awaitable[bool]] | None = None,
        *,
        event_type: type[Event] | None = None,
        adapter_type: type[Adapter[Any, Any]] | None = None,
        max_try_times: int | None = None,
        timeout: int | float = MAX_TIMEOUT,
    ) -> Event[Any]:
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
        _func = wrap_get_func(func, event_type=event_type, adapter_type=adapter_type)

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
                        with anyio.fail_after(start_time + timeout - time.time()):
                            await self._condition.wait()
                    except TimeoutError:
                        break

                if (
                    self._current_event is not None
                    and not self._current_event.__handled__
                    and await _func(self._current_event)
                ):
                    self._current_event.__handled__ = True
                    logger.debug("Event caught", event=self._current_event)
                    return self._current_event

                try_times += 1

        raise GetEventTimeout
