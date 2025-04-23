"""CQHTTP 协议适配器。

本适配器适配了 OneBot v11 协议。
协议详情请参考：[OneBot](https://github.com/howmanybots/onebot/blob/master/README.md)。
"""

import inspect
import json
import sys
import time
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, ClassVar
from typing_extensions import override

import aiohttp
import anyio
from aiohttp import web
from anyio.lowlevel import checkpoint
from pydantic import TypeAdapter

from sekaibot.adapter.utils import WebSocketAdapter
from sekaibot.internal.message import BuildMessageType
from sekaibot.log import logger
from sekaibot.utils import PydanticEncoder

from . import event
from .config import Config
from .event import (
    CQHTTPEvent,
    HeartbeatMetaEvent,
    LifecycleMetaEvent,
    MessageEvent,
    MetaEvent,
    Reply,
)
from .exceptions import ActionFailed, ApiNotAvailable, ApiTimeout, NetworkError
from .message import CQHTTPMessage, CQHTTPMessageSegment

__all__ = ["CQHTTPAdapter"]


EventModels = dict[tuple[str | None, str | None, str | None], type[CQHTTPEvent]]

DETAIL_TYPE_KEYS = ("message_type", "notice_type", "request_type", "meta_event_type")
DEFAULT_EVENT_MODELS: EventModels = {}
for _, model in inspect.getmembers(event, inspect.isclass):
    if issubclass(model, CQHTTPEvent):
        DEFAULT_EVENT_MODELS[model.get_event_type()] = model


class CQHTTPAdapter(WebSocketAdapter[CQHTTPEvent, Config]):  # type: ignore
    """CQHTTP 协议适配器。"""

    name = "cqhttp"
    Config = Config

    event_models: ClassVar[EventModels] = DEFAULT_EVENT_MODELS

    _api_response: dict[str, Any]
    _api_response_cond: anyio.Condition
    _api_id: int = 0

    def __getattr__(self, item: str) -> Callable[..., Awaitable[Any]]:
        """用于调用 API。可以直接通过访问适配器的属性访问对应名称的 API。

        Args:
            item: API 名称。

        Returns:
            用于调用 API 的函数。
        """
        return partial(self.call_api, item)

    @override
    async def startup(self) -> None:
        adapter_type = self.config.adapter_type
        if adapter_type == "ws-reverse":
            adapter_type = "reverse-ws"
        self.adapter_type = adapter_type
        self.host = self.config.host
        self.port = self.config.port
        self.url = self.config.url
        self.reconnect_interval = self.config.reconnect_interval
        self._api_response_cond = anyio.Condition()
        await super().startup()

    @override
    async def reverse_ws_connection_hook(self) -> None:
        logger.info("WebSocket connected!")
        if self.config.access_token:
            assert isinstance(self.websocket, web.WebSocketResponse)
            if (
                self.websocket.headers.get("Authorization", "")
                != f"Bearer {self.config.access_token}"
            ):
                logger.error("WebSocket access token mismatch!")
                await self.websocket.close()

    @override
    async def websocket_connect(self) -> None:
        assert self.session is not None
        logger.info("Tying to connect to WebSocket server...")
        async with self.session.ws_connect(
            f"ws://{self.host}:{self.port}/",
            headers={"Authorization": f"Bearer {self.config.access_token}"}
            if self.config.access_token
            else None,
        ) as self.websocket:
            await self.handle_websocket()

    @override
    async def handle_websocket_msg(self, msg: aiohttp.WSMessage) -> None:
        assert self.websocket is not None
        if msg.type == aiohttp.WSMsgType.TEXT:
            try:
                msg_dict = msg.json()
            except json.JSONDecodeError:
                logger.exception("WebSocket message parsing error, not json")
                return

            if "post_type" in msg_dict:
                await self.handle_cqhttp_event(msg_dict)
            else:
                async with self._api_response_cond:
                    self._api_response = msg_dict
                    self._api_response_cond.notify_all()

        elif msg.type == aiohttp.WSMsgType.ERROR:
            logger.error(
                "WebSocket connection closed with exception",
                exception=self.websocket.exception(),
            )

    def _get_api_echo(self) -> int:
        self._api_id = (self._api_id + 1) % sys.maxsize
        return self._api_id

    @classmethod
    def add_event_model(cls, event_model: type[CQHTTPEvent]) -> None:
        """添加自定义事件模型，事件模型类必须继承于 `CQHTTPEvent`。

        Args:
            event_model: 事件模型类。
        """
        cls.event_models[event_model.get_event_type()] = event_model

    @classmethod
    def get_event_model(
        cls,
        post_type: str | None,
        detail_type: str | None,
        sub_type: str | None,
    ) -> type[CQHTTPEvent]:
        """根据接收到的消息类型返回对应的事件类。

        Args:
            post_type: 请求类型。
            detail_type: 事件类型。
            sub_type: 子类型。

        Returns:
            对应的事件类。
        """
        event_model = (
            cls.event_models.get((post_type, detail_type, sub_type))
            or cls.event_models.get((post_type, detail_type, None))
            or cls.event_models.get((post_type, None, None))
        )
        return event_model or cls.event_models[(None, None, None)]

    async def _get_reply(self, event: MessageEvent) -> None:
        """检查消息中存在的回复，去除并赋值 `event.reply`, `event.to_me`。

        Args:
            bot: Bot 对象
            event: MessageEvent 对象
        """
        try:
            index = [x.type == "reply" for x in event.message].index(True)
        except ValueError:
            return
        msg_seg = event.message[index]
        try:
            event.reply = TypeAdapter(Reply).validate_python(
                await self.get_msg(message_id=int(msg_seg.data["id"]))
            )
        except Exception as e:
            logger.warning(f"Error when getting message reply info: {e!r}", exc_info=e)
            return

        if event.reply.sender.user_id is not None:
            # ensure string comparation
            if str(event.reply.sender.user_id) == str(event.self_id):
                event.to_me = True
            del event.message[index]

            if (
                len(event.message) > index
                and event.message[index].type == "at"
                and event.message[index].data.get("qq") == str(event.reply.sender.user_id)
            ):
                del event.message[index]

        if len(event.message) > index and event.message[index].type == "text":
            event.message[index].data["text"] = event.message[index].data["text"].lstrip()
            if not event.message[index].data["text"]:
                del event.message[index]

        if not event.message:
            event.message.append(CQHTTPMessageSegment.text(""))

    async def _get_at_me(self, event: MessageEvent) -> None:
        """检查消息开头或结尾是否存在 @机器人，去除并赋值 `event.to_me`。

        Args:
            bot: Bot 对象
            event: MessageEvent 对象
        """
        if not isinstance(event, MessageEvent):
            return

        # ensure message not empty
        if not event.message:
            event.message.append(CQHTTPMessageSegment.text(""))

        if event.message_type == "private":
            event.to_me = True
        else:

            def _is_at_me_seg(segment: CQHTTPMessageSegment) -> bool:
                return segment.type == "at" and str(segment.data.get("qq", "")) == str(
                    event.self_id
                )

            # check the first segment
            if _is_at_me_seg(event.message[0]):
                event.to_me = True
                event.message.pop(0)
                if event.message and event.message[0].type == "text":
                    event.message[0].data["text"] = event.message[0].data["text"].lstrip()
                    if not event.message[0].data["text"]:
                        del event.message[0]
                if event.message and _is_at_me_seg(event.message[0]):
                    event.message.pop(0)
                    if event.message and event.message[0].type == "text":
                        event.message[0].data["text"] = event.message[0].data["text"].lstrip()
                        if not event.message[0].data["text"]:
                            del event.message[0]

            if not event.to_me:
                # check the last segment
                i = -1
                last_msg_seg = event.message[i]
                if (
                    last_msg_seg.type == "text"
                    and not last_msg_seg.data["text"].strip()
                    and len(event.message) >= 2  # noqa: PLR2004
                ):
                    i -= 1
                    last_msg_seg = event.message[i]

                if _is_at_me_seg(last_msg_seg):
                    event.to_me = True
                    del event.message[i:]

            if not event.message:
                event.message.append(CQHTTPMessageSegment.text(""))

    async def handle_cqhttp_event(self, msg: dict[str, Any]) -> None:
        """处理 CQHTTP 事件。

        Args:
            msg: 接收到的信息。
        """
        post_type = msg.get("post_type")
        if post_type is None:
            event_class = self.get_event_model(None, None, None)
        else:
            detail_type: str | None = None
            for key in DETAIL_TYPE_KEYS:
                detail_type = msg.get(key)
                if detail_type is not None:
                    break
            event_class = self.get_event_model(
                post_type,
                detail_type or msg.get(post_type + "_type"),
                msg.get("sub_type"),
            )

        cqhttp_event = event_class(adapter=self, **msg)

        if cqhttp_event.post_type == "meta_event":
            # meta_event 不交由插件处理
            assert isinstance(cqhttp_event, MetaEvent)
            if cqhttp_event.meta_event_type == "lifecycle":
                assert isinstance(cqhttp_event, LifecycleMetaEvent)
                if cqhttp_event.sub_type == "connect":
                    logger.info(
                        "WebSocket connection from CQHTTP Bot accepted!",
                        id=msg.get("self_id"),
                    )
            elif cqhttp_event.meta_event_type == "heartbeat":
                assert isinstance(cqhttp_event, HeartbeatMetaEvent)
                if cqhttp_event.status.good and cqhttp_event.status.online:
                    pass
                else:
                    logger.error(
                        "CQHTTP Bot status is not good",
                        status=cqhttp_event.status.model_dump(),
                    )
        else:
            if isinstance(cqhttp_event, MessageEvent):
                await self._get_reply(cqhttp_event)
                await self._get_at_me(cqhttp_event)
            await self.handle_event(cqhttp_event)

    @override
    async def _call_api(self, api: str, **params: Any) -> Any:
        """调用 CQHTTP API，协程会等待直到获得 API 响应。

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
        assert self.websocket is not None
        api_echo = self._get_api_echo()
        try:
            await self.websocket.send_str(
                json.dumps(
                    {"action": api, "params": params, "echo": api_echo},
                    cls=PydanticEncoder,
                )
            )
        except Exception as e:
            raise NetworkError from e

        start_time = time.time()
        while True:
            await checkpoint()
            if time.time() - start_time > self.config.api_timeout:
                break
            async with self._api_response_cond:
                try:
                    with anyio.fail_after(start_time + self.config.api_timeout - time.time()):
                        await self._api_response_cond.wait()
                except TimeoutError:
                    break
                if self._api_response["echo"] == api_echo:
                    if self._api_response.get("retcode") == ApiNotAvailable.ERROR_CODE:
                        raise ApiNotAvailable(resp=self._api_response)
                    if self._api_response.get("status") == "failed":
                        raise ActionFailed(resp=self._api_response)
                    return self._api_response.get("data")

        raise ApiTimeout

    @override
    async def send(  # type: ignore
        self,
        event: CQHTTPEvent,
        message: BuildMessageType[CQHTTPMessageSegment],
        at_sender: bool = False,
        reply_message: bool = False,
        **params: Any,  # extra options passed to send_msg API
    ) -> Any:
        """默认回复消息处理函数。"""
        event_dict = event.model_dump()

        if "message_id" not in event_dict:
            reply_message = False  # if no message_id, force disable reply_message

        if "user_id" in event_dict:  # copy the user_id to the API params if exists
            params.setdefault("user_id", event_dict["user_id"])
        else:
            at_sender = False  # if no user_id, force disable at_sender

        if "group_id" in event_dict:  # copy the group_id to the API params if exists
            params.setdefault("group_id", event_dict["group_id"])

        if "message_type" in event_dict:
            params.setdefault("message_type", event_dict["message_type"])

        if "message_type" not in params:
            if params.get("group_id") is not None:
                params["message_type"] = "group"
            elif params.get("user_id") is not None:
                params["message_type"] = "private"
            else:
                raise ValueError("Cannot guess message type to reply!")

        full_message = CQHTTPMessage()  # create a new message with at sender segment
        if reply_message:
            full_message += CQHTTPMessageSegment.reply(event_dict["message_id"])
        if at_sender and params["message_type"] != "private":
            full_message += CQHTTPMessageSegment.at(params["user_id"]) + " "
        full_message += message
        params.setdefault("message", full_message)

        return await self.send_msg(**params)
