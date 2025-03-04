import asyncio
import time
from contextlib import AsyncExitStack
from collections import defaultdict
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    overload,
)

from .exceptions import (
    GetEventTimeout,
    StopException,
    SkipException,
    PruningException,
    JumpToException,
)
from ._types import EventT
from .utils import validate_instance, wrap_get_func
from .dependencies import solve_dependencies
from .event import Event

if TYPE_CHECKING:
    from .bot import Bot

class Manager():
    bot: "Bot"

    node_state: Dict[str, Any]
    _condition: asyncio.Condition
    _current_event: Event | None

    _handle_event_tasks: Set[
        "asyncio.Task[None]"
    ] 

    def __init__(self, bot: "Bot"):
        self.bot = bot
        self.node_state = defaultdict(lambda: None)
        self._condition = asyncio.Condition()
        self._handle_event_tasks = set()

    async def handle_event(
        self,
        current_event: Event,
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
            self.bot.logger.info(
                "Event received from adapter",
                current_event=current_event,
            )

        if handle_get:
            _handle_event_task = asyncio.create_task(self._handle_event())
            self._handle_event_tasks.add(_handle_event_task)
            _handle_event_task.add_done_callback(self._handle_event_tasks.discard)
            await asyncio.sleep(0)
            async with self._condition:
                self._current_event = current_event
                self._condition.notify_all()
        else:
            _handle_event_task = asyncio.create_task(self._handle_event(current_event))
            self._handle_event_tasks.add(_handle_event_task)
            _handle_event_task.add_done_callback(self._handle_event_tasks.discard)

    async def _handle_event(
        self, 
        current_event: Event | None = None, 
    ) -> None:
        if current_event is None:
            async with self._condition:
                await self._condition.wait()
                assert self._current_event is not None
                current_event = self._current_event
            if current_event.__handled__:
                return

        '''for _hook_func in self._event_preprocessor_hooks:
            await _hook_func(current_event)'''
        _nodes_list = self.bot.nodes_list
        index = 0
        while index < len(_nodes_list):
            node_priority, pruning_node = _nodes_list[index]
            self.bot.logger.debug("Checking for matching nodes", priority=node_priority)
            #if validate_instance(obj=current_event, type_check=node.event_type):
            try:
                async with AsyncExitStack() as stack:
                    _node = await solve_dependencies(
                        node_priority,
                        use_cache=True,
                        stack=stack,
                        dependency_cache={
                            Bot: self,
                            Event: current_event,
                        },
                    )
                    if _node.name not in self.node_state:
                        node_state = _node.__init_state__()
                        if node_state is not None:
                            self.node_state[_node.name] = node_state
                    if await _node.rule():
                        self.bot.logger.info("Event will be handled by node", node=_node)
                        try:
                            await _node.handle()
                        finally:
                            if _node.block:
                                break
            except SkipException:
                # 插件要求跳过自身继续当前事件传播或跳转事件
                next_index = index + 1
            except StopException:
                # 插件要求停止当前事件传播
                break
            except PruningException:
                # 插件要求剪枝
                next_index = pruning_node if pruning_node != -1 else None
            except JumpToException as jump_to_node:
                # 插件要求跳转事件
                jump_to_index = {s.__name__: i for i, (s, _) in enumerate(_nodes_list)}.get(jump_to_node.node, None)
                if jump_to_index is not None:
                    if jump_to_index > index:
                        next_index = jump_to_index
                    else:
                        self.bot.logger.warning("The node to jump to is before the current node", node=_nodes_list[jump_to_index])
                        next_index = index + 1
                else:
                    self.bot.logger.warning("The node to jump to does not exist", node_name=jump_to_node.node)
                    next_index = index + 1
            except Exception:
                self.bot.logger.exception("Exception in node", node=node_priority)
                next_index = index + 1
            else:
                next_index = index + 1

            if next_index is not None:
                index = next_index
            else:
                break
                
        '''for _hook_func in self._event_postprocessor_hooks:
            await _hook_func(current_event)'''

        self.bot.logger.info("Event Finished")

        
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
        event_type: Type[EventT],
        max_try_times: int | None = None,
        timeout: int | float | None = None,
    ) -> EventT: ...

    async def get(
        self,
        func: Callable[[Any], bool | Awaitable[bool]] | None = None,
        *,
        event_type: Type[Event] | None = None,
        max_try_times: int | None = None,
        timeout: int | float | None = None,
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
        while not self.bot.should_exit.is_set():
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
                    return self._current_event

                try_times += 1

        raise GetEventTimeout


    async def cancel_tasks(self) -> None:
        """取消所有未完成的任务"""
        while self._handle_event_tasks:
            task = self._handle_event_tasks.pop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def shutdown(self) -> None:
        """关闭并清理事件。"""
        await self.cancel_tasks()
        self.node_state.clear()
