"""适配器实用工具。

这里定义了一些在编写适配器时常用的基类，适配器开发者可以直接继承自这里的类或者用作参考。
"""

from abc import ABCMeta, abstractmethod
from typing import Generic, Literal
from typing_extensions import override

import aiohttp
import anyio
from aiohttp import web
from anyio.lowlevel import checkpoint
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from sekaibot.internal.adapter import Adapter
from sekaibot.log import logger
from sekaibot.typing import ConfigT, EventT

__all__ = [
    "HttpClientAdapter",
    "HttpServerAdapter",
    "PollingAdapter",
    "WebSocketAdapter",
    "WebSocketClientAdapter",
    "WebSocketServerAdapter",
]


class PollingAdapter(Adapter[EventT, ConfigT], metaclass=ABCMeta):  # type: ignore
    """轮询式适配器示例。"""

    @override
    async def run(self) -> None:
        while True:
            await checkpoint()
            await self.on_tick()

    @abstractmethod
    async def on_tick(self) -> None:
        """当轮询发生。"""


class HttpClientAdapter(PollingAdapter[EventT, ConfigT], metaclass=ABCMeta):
    """HTTP 客户端适配器示例。"""

    session: aiohttp.ClientSession

    @override
    async def startup(self) -> None:
        self.session = aiohttp.ClientSession()

    @override
    async def shutdown(self) -> None:
        await self.session.close()


class WebSocketClientAdapter(Adapter[EventT, ConfigT], metaclass=ABCMeta):  # type: ignore
    """WebSocket 客户端适配器示例。"""

    url: str

    @override
    async def run(self) -> None:
        async with (
            aiohttp.ClientSession() as session,
            session.ws_connect(self.url) as ws,
        ):
            msg: aiohttp.WSMessage
            async for msg in ws:
                await checkpoint()
                if msg.type == aiohttp.WSMsgType.ERROR:
                    break
                await self.handle_response(msg)

    @abstractmethod
    async def handle_response(self, msg: aiohttp.WSMessage) -> None:
        """处理响应。"""


class HttpServerAdapter(Adapter[EventT, ConfigT], metaclass=ABCMeta):  # type: ignore
    """HTTP 服务端适配器示例。"""

    app: web.Application
    runner: web.AppRunner
    site: web.TCPSite
    host: str
    port: int
    get_url: str
    post_url: str

    @override
    async def startup(self) -> None:
        self.app = web.Application()
        self.app.add_routes(
            [
                web.get(self.get_url, self.handle_response),
                web.post(self.post_url, self.handle_response),
            ]
        )

    @override
    async def run(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

    @override
    async def shutdown(self) -> None:
        await self.runner.cleanup()

    @abstractmethod
    async def handle_response(self, request: web.Request) -> web.StreamResponse:
        """处理响应。"""


class WebSocketServerAdapter(Adapter[EventT, ConfigT], metaclass=ABCMeta):  # type: ignore
    """WebSocket 服务端适配器示例。"""

    app: web.Application
    runner: web.AppRunner
    site: web.TCPSite
    websocket: web.WebSocketResponse
    host: str
    port: int
    url: str

    _msg_send_stream: MemoryObjectSendStream[aiohttp.WSMessage]
    _msg_receive_stream: MemoryObjectReceiveStream[aiohttp.WSMessage]

    @override
    async def startup(self) -> None:
        self.app = web.Application()
        self.app.add_routes([web.get(self.url, self.handle_response)])
        self._msg_send_stream, self._msg_receive_stream = (
            anyio.create_memory_object_stream(max_buffer_size=float("inf"))
        )

    @override
    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._handle_msg_receive)
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

    @override
    async def shutdown(self) -> None:
        await self.websocket.close()
        await self.site.stop()
        await self.runner.cleanup()
        await self._msg_send_stream.aclose()
        await self._msg_receive_stream.aclose()

    async def handle_response(self, request: web.Request) -> web.WebSocketResponse:
        """处理 WebSocket。"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websocket = ws

        msg: aiohttp.WSMessage
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._msg_send_stream.send(msg)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break

        return ws

    async def _handle_msg_receive(self) -> None:
        async with anyio.create_task_group() as tg, self._msg_receive_stream:
            async for msg in self._msg_receive_stream:
                tg.start_soon(self.handle_ws_response, msg)

    @abstractmethod
    async def handle_ws_response(self, msg: aiohttp.WSMessage) -> None:
        """处理 WebSocket 响应。"""


class WebSocketAdapter(
    Adapter[EventT, ConfigT], Generic[EventT, ConfigT], metaclass=ABCMeta
):  # type: ignore
    """WebSocket 适配器示例。

    同时支持 WebSocket 客户端和服务端。
    """

    websocket: web.WebSocketResponse | aiohttp.ClientWebSocketResponse | None = None

    # ws
    session: aiohttp.ClientSession | None

    # reverse-ws
    app: web.Application | None
    runner: web.AppRunner | None
    site: web.TCPSite | None

    # config
    adapter_type: Literal["ws", "reverse-ws"]
    host: str
    port: int
    url: str
    reconnect_interval: int = 3

    _msg_send_stream: MemoryObjectSendStream[aiohttp.WSMessage]
    _msg_receive_stream: MemoryObjectReceiveStream[aiohttp.WSMessage]

    @override
    async def startup(self) -> None:
        """初始化适配器。"""
        if self.adapter_type == "ws":
            self.session = aiohttp.ClientSession()
        elif self.adapter_type == "reverse-ws":
            self.app = web.Application()
            self.app.add_routes([web.get(self.url, self.handle_reverse_ws_response)])
        else:
            logger.error(
                'Config "adapter_type" must be "ws" or "reverse-ws"',
                adapter_type=self.adapter_type,
            )
        self._msg_send_stream, self._msg_receive_stream = (
            anyio.create_memory_object_stream(max_buffer_size=float("inf"))
        )

    @override
    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._handle_msg_receive)
            if self.adapter_type == "ws":
                while True:
                    try:
                        await self.websocket_connect()
                    except aiohttp.ClientError:
                        logger.exception("WebSocket connection error")
                    await anyio.sleep(self.reconnect_interval)
            elif self.adapter_type == "reverse-ws":
                assert self.app is not None
                self.runner = web.AppRunner(self.app)
                await self.runner.setup()
                self.site = web.TCPSite(self.runner, self.host, self.port)
                await self.site.start()

    @override
    async def shutdown(self) -> None:
        if self.websocket is not None:
            await self.websocket.close()
        if self.adapter_type == "ws":
            if self.session is not None:
                await self.session.close()
        elif self.adapter_type == "reverse-ws":
            if self.site is not None:
                await self.site.stop()
            if self.runner is not None:
                await self.runner.cleanup()
        await self._msg_send_stream.aclose()
        await self._msg_receive_stream.aclose()

    async def handle_reverse_ws_response(
        self, request: web.Request
    ) -> web.WebSocketResponse:
        """处理 aiohttp WebSocket 服务器的接收。"""
        self.websocket = web.WebSocketResponse()
        await self.websocket.prepare(request)
        await self.reverse_ws_connection_hook()
        await self.handle_websocket()
        return self.websocket

    async def reverse_ws_connection_hook(self) -> None:
        """反向 WebSocket 连接建立时的钩子函数。"""
        logger.info("WebSocket connected!")

    async def websocket_connect(self) -> None:
        """创建正向 WebSocket 连接。"""
        assert self.session is not None
        logger.info("Tying to connect to WebSocket server...")
        async with self.session.ws_connect(
            f"ws://{self.host}:{self.port}{self.url}"
        ) as self.websocket:
            await self.handle_websocket()

    async def handle_websocket(self) -> None:
        """处理 WebSocket。"""
        if self.websocket is None or self.websocket.closed:
            return
        async for msg in self.websocket:
            await checkpoint()
            await self._msg_send_stream.send(msg)
        if not self.bot._should_exit.is_set():
            logger.warning("WebSocket connection closed!")

    async def _handle_msg_receive(self) -> None:
        async with anyio.create_task_group() as tg, self._msg_receive_stream:
            async for msg in self._msg_receive_stream:
                tg.start_soon(self.handle_websocket_msg, msg)

    @abstractmethod
    async def handle_websocket_msg(self, msg: aiohttp.WSMessage) -> None:
        """处理 WebSocket 消息。"""
        raise NotImplementedError
