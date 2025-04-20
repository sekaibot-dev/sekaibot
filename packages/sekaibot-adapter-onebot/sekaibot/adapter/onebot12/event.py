"""OneBot 适配器事件。"""
# pyright: reportIncompatibleVariableOverride=false

from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, get_args, get_origin, override

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.fields import FieldInfo

from sekaibot.internal.event import Event as BaseEvent

from .message import OneBotMessage

if TYPE_CHECKING:
    from . import OneBotAdapter  # noqa: F401


class Event(BaseEvent["OneBotAdapter"]):
    """OneBot V12 协议事件，字段与 OneBot 一致

    参考文档：[OneBot 文档](https://12.1bot.dev)
    """

    id: str
    time: datetime
    type: Literal["message", "notice", "request", "meta"]
    detail_type: str
    sub_type: str

    @override
    def get_type(self) -> str:
        return self.type

    @override
    def get_event_name(self) -> str:
        return ".".join(filter(None, (self.type, self.detail_type, self.sub_type)))

    @override
    def get_event_description(self) -> str:
        return str(self.model_dump())

    @override
    def get_message(self) -> OneBotMessage:
        raise ValueError("Event has no message!")

    @override
    def get_user_id(self) -> str:
        raise ValueError("Event has no user_id!")

    @override
    def get_session_id(self) -> str:
        raise ValueError("Event has no session_id!")

    @override
    def is_tome(self) -> bool:
        return False


class BotSelf(BaseModel):
    """机器人自身标识"""

    platform: str
    user_id: str


class ImplVersion(BaseModel):
    """实现版本"""

    impl: str
    version: str
    onebot_version: str


class BotStatus(BaseModel):
    """机器人状态"""

    self: BotSelf
    online: bool


class Status(BaseModel):
    """运行状态"""

    model_config = ConfigDict(extra="allow")

    good: bool
    bots: list[BotStatus]


def _get_literal_field(field: FieldInfo | None) -> str | None:
    if field is None:
        return None
    annotation = field.annotation
    if annotation is None or get_origin(annotation) is not Literal:
        return None
    literal_values = get_args(annotation)
    if len(literal_values) != 1:
        return None
    return literal_values[0]


class OneBotEvent(Event):
    """OneBot 事件基类"""

    id: str
    time: float
    type: Literal["meta", "message", "notice", "request"]
    detail_type: str
    sub_type: str

    @classmethod
    def get_event_type(cls) -> tuple[str | None, str | None, str | None]:
        """获取事件类型。

        Returns:
            事件类型。
        """
        return (
            _get_literal_field(cls.model_fields.get("type")),
            _get_literal_field(cls.model_fields.get("detail_type")),
            _get_literal_field(cls.model_fields.get("sub_type")),
        )


class Reply(BaseModel):
    message_id: str
    user_id: str
    model_config = ConfigDict(extra="allow")


class BotEvent(OneBotEvent):
    """包含 self 字段的机器人事件"""

    self: BotSelf


class MetaEvent(OneBotEvent):
    """元事件"""

    type: Literal["meta"]

    def get_user_id(self) -> str | None:
        """获取事件主体 id 的方法，通常是用户 id 。"""
        return None

    def get_session_id(self) -> str | None:
        """获取会话 id 的方法，用于判断当前事件属于哪一个会话，
        通常是用户 id、群组 id 组合。
        """
        return None

    def get_message(self) -> None:
        """获取事件消息内容的方法。"""
        return None

    def get_plain_text(self) -> str:
        """获取消息纯文本的方法。

        通常不需要修改，默认通过 `get_message().get_plain_text` 获取。
        """
        return None

    def is_tome(self) -> bool:
        """获取事件是否与机器人有关的方法。"""
        return False


class ConnectMetaEvent(MetaEvent):
    """连接事件"""

    detail_type: Literal["connect"]
    version: ImplVersion


class HeartbeatMetaEvent(MetaEvent):
    """心跳事件"""

    detail_type: Literal["heartbeat"]
    interval: int


class StatusUpdateMetaEvent(MetaEvent):
    """状态更新事件"""

    detail_type: Literal["status_update"]
    status: Status


class MessageEvent(BotEvent):
    """消息事件"""

    type: Literal["message"]
    message_id: str
    message: OneBotMessage
    original_message: OneBotMessage
    alt_message: str
    user_id: str

    to_me: bool = False
    """
    :说明: 消息是否与机器人有关

    :类型: ``bool``
    """
    reply: Reply | None = None
    """
    :说明: 消息中提取的回复消息，内容为 ``get_msg`` API 返回结果

    :类型: ``Optional[Reply]``
    """

    @model_validator(mode="before")
    def check_message(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "message" in values:
            values["original_message"] = deepcopy(values["message"])
        return values

    @override
    def get_message(self) -> OneBotMessage:
        return self.message

    @override
    def get_user_id(self) -> str:
        return self.user_id

    @override
    def get_session_id(self) -> str:
        return "{self.user_id}"

    @override
    def is_tome(self) -> bool:
        return self.to_me


class PrivateMessageEvent(MessageEvent):
    """私聊消息"""

    detail_type: Literal["private"]

    @override
    def get_event_description(self) -> str:
        return (
            f"Message {self.message_id} from {self.user_id} "
            + repr(self.original_message)
        )
    @override
    def get_user_id(self) -> str:
        return f"private:{self.user_id}"

class GroupMessageEvent(MessageEvent):
    """群消息"""

    detail_type: Literal["group"]
    group_id: str

    @override
    def get_event_description(self) -> str:
        return (
            f"Message {self.message_id} from {self.user_id}@[group:{self.group_id}] "
            + repr(self.original_message)
        )

    @override
    def get_session_id(self) -> str:
        return f"group:{self.group_id}:{self.user_id}"


class ChannelMessageEvent(MessageEvent):
    """频道消息"""

    detail_type: Literal["channel"]
    guild_id: str
    channel_id: str

    @override
    def get_event_description(self) -> str:
        return (
            f"Message {self.message_id} from {self.user_id}@"
            f"[guild:{self.guild_id}, channel:{self.channel_id}] {repr(self.original_message)}"
        )

    @override
    def get_session_id(self) -> str:
        return f"guild:{self.guild_id}:channel:{self.channel_id}:{self.user_id}"


class NoticeEvent(BotEvent):
    """通知事件"""

    type: Literal["notice"]


class FriendIncreaseEvent(NoticeEvent):
    """好友增加事件"""

    detail_type: Literal["friend_increase"]
    user_id: str


class FriendDecreaseEvent(NoticeEvent):
    """好友减少事件"""

    detail_type: Literal["friend_decrease"]
    user_id: str


class PrivateMessageDeleteEvent(NoticeEvent):
    """私聊消息删除"""

    detail_type: Literal["private_message_delete"]
    message_id: str
    user_id: str


class GroupMemberIncreaseEvent(NoticeEvent):
    """群成员增加事件"""

    detail_type: Literal["group_member_increase"]
    group_id: str
    user_id: str
    operator_id: str


class GroupMemberDecreaseEvent(NoticeEvent):
    """群成员减少事件"""

    detail_type: Literal["group_member_decrease"]
    group_id: str
    user_id: str
    operator_id: str


class GroupMessageDeleteEvent(NoticeEvent):
    """群消息删除事件"""

    detail_type: Literal["group_message_delete"]
    group_id: str
    message_id: str
    user_id: str
    operator_id: str


class GuildMemberIncreaseEvent(NoticeEvent):
    """群组成员增加事件"""

    detail_type: Literal["guild_member_increase"]
    guild_id: str
    user_id: str
    operator_id: str


class GuildMemberDecreaseEvent(NoticeEvent):
    """群组成员减少事件"""

    detail_type: Literal["guild_member_decrease"]
    guild_id: str
    user_id: str
    operator_id: str


class ChannelMemberIncreaseEvent(NoticeEvent):
    """频道成员增加事件"""

    detail_type: Literal["channel_member_increase"]
    guild_id: str
    channel_id: str
    user_id: str
    operator_id: str


class ChannelMemberDecreaseEvent(NoticeEvent):
    """频道成员减少事件"""

    detail_type: Literal["channel_member_decrease"]
    guild_id: str
    channel_id: str
    user_id: str
    operator_id: str


class ChannelMessageDeleteEvent(NoticeEvent):
    """频道消息删除事件"""

    detail_type: Literal["channel_message_delete"]
    guild_id: str
    channel_id: str
    message_id: str
    user_id: str
    operator_id: str


class ChannelCreateEvent(NoticeEvent):
    """频道新建事件"""

    detail_type: Literal["channel_create"]
    guild_id: str
    channel_id: str
    operator_id: str


class ChannelDeleteEvent(NoticeEvent):
    """频道删除事件"""

    detail_type: Literal["channel_delete"]
    guild_id: str
    channel_id: str
    operator_id: str


class RequestEvent(BotEvent):
    """请求事件"""

    type: Literal["request"]
