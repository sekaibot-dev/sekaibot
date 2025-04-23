"""AliceBot 协议适配器。

所有协议适配器都必须继承自 `Adapter` 基类。
"""

import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    final,
    overload,
)

import anyio
from exceptiongroup import catch

from sekaibot.exceptions import MockApiException
from sekaibot.internal.event import Event
from sekaibot.internal.message import BuildMessageType, MessageSegmentT
from sekaibot.log import logger
from sekaibot.typing import CalledAPIHook, CallingAPIHook, ConfigT, EventT
from sekaibot.utils import flatten_exception_group, handle_exception, is_config_class

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Adapter"]

if os.getenv("SEKAIBOT_DEV") == "1":  # pragma: no cover
    # 当处于开发环境时，使用 pkg_resources 风格的命名空间包
    __import__("pkg_resources").declare_namespace(__name__)


class Adapter(ABC, Generic[EventT, ConfigT]):
    """协议适配器基类。

    Attributes:
        name: 适配器的名称。
        bot: 当前的机器人对象。
    """

    name: str
    bot: "Bot"
    Config: type[ConfigT]

    _calling_api_hooks: ClassVar[set[CallingAPIHook]] = set()
    _called_api_hooks: ClassVar[set[CalledAPIHook]] = set()

    def __init__(self, bot: "Bot") -> None:
        """初始化。

        Args:
            bot: 当前机器人对象。
        """
        if not hasattr(self, "name"):
            self.name = self.__class__.__name__
        self.bot: Bot = bot
        self.handle_event = self.bot.manager.handle_event

    @property
    def config(self) -> ConfigT:
        """适配器配置。"""
        default: Any = None
        config_class = getattr(self, "Config", None)
        if is_config_class(config_class):
            return getattr(
                self.bot.config.adapter,
                config_class.__config_name__,
                default,
            )
        return default

    @final
    async def safe_run(self) -> None:
        """附带有异常处理和重试机制的安全运行适配器。"""
        retries = 0
        while not self.bot._should_exit.is_set():
            if retries <= self.bot.config.bot.adapter_max_retries:
                with catch(
                    {
                        Exception: handle_exception(
                            "Run adapter failed", adapter_name=self.__class__.__name__
                        )
                    }
                ):
                    await self.run()
                if self.bot._should_exit.is_set():
                    break
                logger.info(
                    "Retry running the adapter...",
                    adapter_name=self.__class__.__name__,
                    retries=retries,
                )
                retries += 1
            else:
                logger.warning(
                    "Adapter run failed after retries",
                    adapter_name=self.__class__.__name__,
                )
                break

    @abstractmethod
    async def run(self) -> None:
        """适配器运行方法，适配器开发者必须实现该方法。

        适配器运行过程中保持保持运行，当此方法结束后， AliceBot 不会自动重新启动适配器。
        """
        raise NotImplementedError

    async def startup(self) -> None:
        """在适配器开始运行前运行的方法，用于初始化适配器。

        AliceBot 依次运行并等待所有适配器的 `startup()` 方法，待运行完毕后再创建 `run()` 任务。
        """

    async def shutdown(self) -> None:
        """在适配器结束运行时运行的方法，用于安全地关闭适配器。

        AliceBot 在接收到系统的结束信号后先发送 cancel 请求给 run 任务。
        在所有适配器都停止运行后，会依次运行并等待所有适配器的 `shutdown()` 方法。
        当强制退出时此方法可能未被执行。
        """

    @abstractmethod
    async def _call_api(self, api: str, **params: Any) -> Any:
        """调用 OneBot API，协程会等待直到获得 API 响应。"""
        raise NotImplementedError

    async def call_api(self, api: str, **params: Any) -> Any:
        """调用机器人 API 接口，可以通过该函数或直接通过 bot 属性进行调用

        Args:
            api: API 名称
            params: API 数据

        用法:
            ```python
            await bot.call_api("send_msg", message="hello world")
            await bot.send_msg(message="hello world")
            ```
        """
        result: Any = None
        skip_calling_api: bool = False
        exception: Exception | None = None

        if self._calling_api_hooks:
            logger.debug("Running CallingAPI hooks...")

            def _handle_mock_api_exception(
                exc_group: BaseExceptionGroup[MockApiException],
            ) -> None:
                nonlocal skip_calling_api, result

                excs = [
                    exc
                    for exc in flatten_exception_group(exc_group)
                    if isinstance(exc, MockApiException)
                ]
                if not excs:
                    return
                if len(excs) > 1:
                    logger.warning(
                        "Multiple hooks want to mock API result. Use the first one."
                    )

                skip_calling_api = True
                result = excs[0].result # type: ignore

                logger.debug(
                    f"Calling API {api} is cancelled. Return {result!r} instead."
                )

            with catch(
                {
                    MockApiException: _handle_mock_api_exception,
                    Exception: handle_exception(
                        "Error when running CallingAPI hook. Running cancelled!"
                    ),
                }
            ):
                async with anyio.create_task_group() as tg:
                    for calling_hook in self._calling_api_hooks:
                        tg.start_soon(calling_hook, self, api, params) # type: ignore

        if not skip_calling_api:
            try:
                result = await self._call_api(api, **params)
            except Exception as e:
                exception = e

        if self._called_api_hooks:
            logger.debug("Running CalledAPI hooks...")

            def _handle_mock_api_exception(
                exc_group: BaseExceptionGroup[MockApiException],
            ) -> None:
                nonlocal result, exception

                excs = [
                    exc
                    for exc in flatten_exception_group(exc_group)
                    if isinstance(exc, MockApiException)
                ]
                if not excs:
                    return
                if len(excs) > 1:
                    logger.warning(
                        "Multiple hooks want to mock API result. Use the first one."
                    )

                result = excs[0].result # type: ignore
                exception = None
                logger.debug(
                    f"Calling API {api} result is mocked. Return {result} instead."
                )

            with catch(
                {
                    MockApiException: _handle_mock_api_exception,
                    Exception: handle_exception(
                        "Error when running CalledAPI hook. Running cancelled!"
                    ),
                }
            ):
                async with anyio.create_task_group() as tg:
                    for called_hook in self._called_api_hooks:
                        tg.start_soon(called_hook, self, exception, api, params, result) # type: ignore

        if exception:
            raise exception
        return result

    @abstractmethod
    async def send(
        self,
        event: Event[Any],
        message: BuildMessageType[MessageSegmentT],
        **kwargs: Any,
    ) -> Any:
        """调用机器人基础发送消息接口

        Args:
            event: 上报事件
            message: 要发送的消息
            kwargs: 任意额外参数
        """
        raise NotImplementedError

    @overload
    async def get(
        self,
        func: Callable[[EventT], bool | Awaitable[bool]] | None = None,
        *,
        event_type: None = None,
        max_try_times: int | None = None,
        timeout: float | None = None,
    ) -> EventT: ...

    @overload
    async def get(
        self,
        func: Callable[[Event[Any]], bool | Awaitable[bool]] | None = None,
        *,
        event_type: type[Event[Any]],
        max_try_times: int | None = None,
        timeout: float | None = None,
    ) -> Event[Any]: ...

    @final
    async def get(
        self,
        func: Callable[[Any], bool | Awaitable[bool]] | None = None,
        *,
        event_type: Any = None,
        max_try_times: int | None = None,
        timeout: float | None = None,
    ) -> Event[Any]:
        """获取满足指定条件的的事件，协程会等待直到适配器接收到满足条件的事件、超过最大事件数或超时。

        类似 `Bot` 类的 `get()` 方法，但是隐含了判断产生事件的适配器是本适配器。
        等效于 `Bot` 类的 `get()` 方法传入 adapter_type 为本适配器类型。

        Args:
            func: 协程或者函数，函数会被自动包装为协程执行。
                要求接受一个事件作为参数，返回布尔值。
                当协程返回 `True` 时返回当前事件。
                当为 `None` 时相当于输入对于任何事件均返回真的协程，即返回适配器接收到的下一个事件。
            event_type: 当指定时，只接受指定类型的事件，先于 func 条件生效。默认为 `None`。
            max_try_times: 最大事件数。
            timeout: 超时时间。

        Returns:
            返回满足 func 条件的事件。

        Raises:
            GetEventTimeout: 超过最大事件数或超时。
        """
        return await self.bot.manager.get(
            func,
            event_type=event_type,
            adapter_type=type(self), # type: ignore
            max_try_times=max_try_times,
            timeout=timeout,
        ) # type: ignore

    @classmethod
    def calling_api_hook(cls, func: CallingAPIHook) -> CallingAPIHook:
        """调用 api 预处理。

        钩子函数Args:

        - bot: 当前 bot 对象
        - api: 调用的 api 名称
        - data: api 调用的参数字典
        """
        cls._calling_api_hooks.add(func)
        return func

    @classmethod
    def called_api_hook(cls, func: CalledAPIHook) -> CalledAPIHook:
        """调用 api 后处理。

        钩子函数Args:

        - bot: 当前 bot 对象
        - exception: 调用 api 时发生的错误
        - api: 调用的 api 名称
        - data: api 调用的参数字典
        - result: api 调用的返回
        """
        cls._called_api_hooks.add(func)
        return func
