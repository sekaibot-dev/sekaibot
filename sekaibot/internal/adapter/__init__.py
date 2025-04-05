"""AliceBot 协议适配器。

所有协议适配器都必须继承自 `Adapter` 基类。
"""

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Generic, final

import anyio
from exceptiongroup import catch

from sekaibot.exceptions import MockApiException
from sekaibot.internal.event import Event
from sekaibot.internal.message import BuildMessageType, MessageSegmentT
from sekaibot.log import logger
from sekaibot.typing import CalledAPIHook, CallingAPIHook, ConfigT
from sekaibot.utils import flatten_exception_group, handle_exception, is_config_class

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Adapter"]

if os.getenv("ALICEBOT_DEV") == "1":  # pragma: no cover
    # 当处于开发环境时，使用 pkg_resources 风格的命名空间包
    __import__("pkg_resources").declare_namespace(__name__)


class Adapter(ABC, Generic[MessageSegmentT, ConfigT]):
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
        """附带有异常处理地安全运行适配器。"""
        try:
            await self.run()
        except Exception:
            logger.exception("Run adapter failed", adapter_name=self.__class__.__name__)

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

        参数:
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
                elif len(excs) > 1:
                    logger.warning("Multiple hooks want to mock API result. Use the first one.")

                skip_calling_api = True
                result = excs[0].result

                logger.debug(f"Calling API {api} is cancelled. Return {result!r} instead.")

            with catch(
                {
                    MockApiException: _handle_mock_api_exception,
                    Exception: handle_exception(
                        "Error when running CallingAPI hook. Running cancelled!"
                    ),
                }
            ):
                async with anyio.create_task_group() as tg:
                    for hook in self._calling_api_hooks:
                        tg.start_soon(hook, self, api, params)

        if not skip_calling_api:
            try:
                result = await self._call_api(self, api, **params)
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
                elif len(excs) > 1:
                    logger.warning("Multiple hooks want to mock API result. Use the first one.")

                result = excs[0].result
                exception = None
                logger.debug(f"Calling API {api} result is mocked. Return {result} instead.")

            with catch(
                {
                    MockApiException: _handle_mock_api_exception,
                    Exception: handle_exception(
                        "Error when running CalledAPI hook. Running cancelled!"
                    ),
                }
            ):
                async with anyio.create_task_group() as tg:
                    for hook in self._called_api_hooks:
                        tg.start_soon(hook, self, exception, api, params, result)

        if exception:
            raise exception
        return result

    @abstractmethod
    async def send(
        self,
        event: Event,
        message: BuildMessageType[MessageSegmentT],
        **kwargs: Any,
    ) -> Any:
        """调用机器人基础发送消息接口

        参数:
            event: 上报事件
            message: 要发送的消息
            kwargs: 任意额外参数
        """
        raise NotImplementedError

    @classmethod
    def calling_api_hook(cls, func: CallingAPIHook) -> CallingAPIHook:
        """调用 api 预处理。

        钩子函数参数:

        - bot: 当前 bot 对象
        - api: 调用的 api 名称
        - data: api 调用的参数字典
        """
        cls._calling_api_hooks.add(func)
        return func

    @classmethod
    def called_api_hook(cls, func: CalledAPIHook) -> CalledAPIHook:
        """调用 api 后处理。

        钩子函数参数:

        - bot: 当前 bot 对象
        - exception: 调用 api 时发生的错误
        - api: 调用的 api 名称
        - data: api 调用的参数字典
        - result: api 调用的返回
        """
        cls._called_api_hooks.add(func)
        return func
