"""CQHTTP 适配器事件。"""
# pyright: reportIncompatibleVariableOverride=false

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal, get_args, get_origin
from typing_extensions import override

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.fields import FieldInfo

from sekaibot.internal.event import Event as BaseEvent

from .message import CQHTTPMessage

if TYPE_CHECKING:
    from . import CQHTTPAdapter


class CQHTTPEvent(BaseEvent["CQHTTPAdapter"]):
    """OneBot v11 协议事件，字段与 OneBot 一致。各事件字段参考 [OneBot 文档]

    [OneBot 文档]: https://github.com/botuniverse/onebot-11/blob/master/README.md
    """

    __event__ = ""
    type: str | None = Field(alias="post_type")
    time: int
    self_id: int
    post_type: str

    def get_type(self) -> str:
        """获取事件类型"""
        return self.post_type

    @override
    def get_event_name(self) -> str:
        return self.post_type

    @override
    def get_event_description(self) -> str:
        return str(self.model_dump())

    @override
    def get_message(self) -> CQHTTPMessage:
        raise ValueError("Event has no message!")

    @override
    def get_user_id(self) -> str:
        raise ValueError("Event has no context!")

    @override
    def get_session_id(self) -> str:
        raise ValueError("Event has no context!")

    @override
    def is_tome(self) -> bool:
        return False

    @classmethod
    def get_event_type(cls) -> tuple[str | None, str | None, str | None]:
        """获取事件类型。

        Returns:
            事件类型。
        """
        post_type = _get_literal_field(cls.model_fields.get("post_type"))
        if post_type is None:
            return (None, None, None)
        return (
            post_type,
            _get_literal_field(cls.model_fields.get(post_type + "_type")),
            _get_literal_field(cls.model_fields.get("sub_type")),
        )


class Sender(BaseModel):
    """发送人信息"""

    user_id: int | None = None
    nickname: str | None = None
    card: str | None = None
    sex: Literal["male", "female", "unknown"] | None = None
    age: int | None = None
    area: str | None = None
    level: str | None = None
    role: str | None = None
    title: str | None = None


class Reply(BaseModel):
    """回复信息"""

    model_config = ConfigDict(extra="allow")

    time: int
    message_type: str
    message_id: int
    real_id: int
    sender: Sender
    message: CQHTTPMessage


class Anonymous(BaseModel):
    """匿名信息"""

    id: int
    name: str
    flag: str


class File(BaseModel):
    """文件信息"""

    id: str
    name: str
    size: int
    busid: int


class Status(BaseModel):
    """状态信息"""

    model_config = ConfigDict(extra="allow")

    online: bool
    good: bool


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


class MessageEvent(CQHTTPEvent):
    """消息事件"""

    __event__ = "message"
    post_type: Literal["message"]
    message_type: Literal["private", "group"]
    sub_type: str
    message_id: int
    user_id: int
    message: CQHTTPMessage
    original_message: CQHTTPMessage
    raw_message: str
    font: int
    sender: Sender
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
    @classmethod
    def check_message(cls, values: dict[str, Any]) -> dict[str, Any]:
        """校验message"""
        if "message" in values:
            values["original_message"] = deepcopy(values["message"])
        return values

    @override
    def get_event_name(self) -> str:
        sub_type = getattr(self, "sub_type", None)
        return f"{self.post_type}.{self.message_type}" + (f".{sub_type}" if sub_type else "")

    @override
    def get_message(self) -> CQHTTPMessage:
        return self.message

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)

    @override
    def get_session_id(self) -> str:
        if group_id := getattr(self, "group_id", None):
            return f"group_{group_id}_{self.get_user_id()}"
        return self.get_user_id()

    @override
    def is_tome(self) -> bool:
        return self.to_me


class PrivateMessageEvent(MessageEvent):
    """私聊消息"""

    __event__ = "message.private"
    message_type: Literal["private"]
    sub_type: Literal["friend", "group", "other"]

    @override
    def get_event_description(self) -> str:
        return f">> MsgID:[{self.message_id}] | User:[{self.user_id}]\n>> " + repr(
            self.original_message
        )


class GroupMessageEvent(MessageEvent):
    """群消息"""

    __event__ = "message.group"
    message_type: Literal["group"]
    sub_type: Literal["normal", "anonymous", "notice"]
    group_id: int
    anonymous: Anonymous | None = None

    @override
    def get_event_description(self) -> str:
        return (
            f">> MsgID:[{self.message_id}] | User:[{self.user_id}] | Group:[{self.group_id}]\n>> "
            + repr(self.original_message)
        )


class NoticeEvent(CQHTTPEvent):
    """通知事件"""

    __event__ = "notice"
    post_type: Literal["notice"]
    notice_type: str

    @override
    def get_event_name(self) -> str:
        sub_type = getattr(self, "sub_type", None)
        return f"{self.post_type}.{self.notice_type}" + (f".{sub_type}" if sub_type else "")

    @override
    def get_session_id(self) -> str:
        if group_id := getattr(self, "group_id", None):
            return f"group_{group_id}_{self.get_user_id()}"
        return self.get_user_id()


class GroupUploadNoticeEvent(NoticeEvent):
    """群文件上传"""

    __event__ = "notice.group_upload"
    notice_type: Literal["group_upload"]
    user_id: int
    group_id: int
    file: File

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class GroupAdminNoticeEvent(NoticeEvent):
    """群管理员变动"""

    __event__ = "notice.group_admin"
    notice_type: Literal["group_admin"]
    sub_type: Literal["set", "unset"]
    user_id: int
    group_id: int

    @override
    def is_tome(self) -> bool:
        return self.user_id == self.self_id

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class GroupDecreaseNoticeEvent(NoticeEvent):
    """群成员减少"""

    __event__ = "notice.group_decrease"
    notice_type: Literal["group_decrease"]
    sub_type: Literal["leave", "kick", "kick_me"]
    group_id: int
    operator_id: int
    user_id: int

    @override
    def is_tome(self) -> bool:
        return self.user_id == self.self_id

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class GroupIncreaseNoticeEvent(NoticeEvent):
    """群成员增加"""

    __event__ = "notice.group_increase"
    notice_type: Literal["group_increase"]
    sub_type: Literal["approve", "invite"]
    group_id: int
    operator_id: int
    user_id: int

    @override
    def is_tome(self) -> bool:
        return self.user_id == self.self_id

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class GroupBanNoticeEvent(NoticeEvent):
    """群禁言"""

    __event__ = "notice.group_ban"
    notice_type: Literal["group_ban"]
    sub_type: Literal["ban", "lift_ban"]
    group_id: int
    operator_id: int
    user_id: int
    duration: int

    @override
    def is_tome(self) -> bool:
        return self.user_id == self.self_id

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class FriendAddNoticeEvent(NoticeEvent):
    """好友添加"""

    __event__ = "notice.friend_add"
    notice_type: Literal["friend_add"]
    user_id: int

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class GroupRecallNoticeEvent(NoticeEvent):
    """群消息撤回"""

    __event__ = "notice.group_recall"
    notice_type: Literal["group_recall"]
    group_id: int
    operator_id: int
    user_id: int
    message_id: int

    @override
    def is_tome(self) -> bool:
        return self.user_id == self.self_id

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class FriendRecallNoticeEvent(NoticeEvent):
    """好友消息撤回"""

    __event__ = "notice.friend_recall"
    notice_type: Literal["friend_recall"]
    user_id: int
    message_id: int

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


class NotifyEvent(NoticeEvent):
    """提醒事件"""

    __event__ = "notice.notify"
    notice_type: Literal["notify"]
    sub_type: str
    user_id: int
    group_id: int | None

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)

    @override
    def get_session_id(self) -> str:
        if group_id := getattr(self, "group_id", None):
            return f"group_{group_id}_{self.get_user_id()}"
        return self.get_user_id()


class PokeNotifyEvent(NotifyEvent):
    """戳一戳"""

    __event__ = "notice.notify.poke"
    sub_type: Literal["poke"]
    target_id: int
    group_id: int | None = None

    @override
    def is_tome(self) -> bool:
        return self.target_id == self.self_id


class GroupLuckyKingNotifyEvent(NotifyEvent):
    """群红包运气王"""

    __event__ = "notice.notify.lucky_king"
    sub_type: Literal["lucky_king"]
    group_id: int
    target_id: int

    @override
    def is_tome(self) -> bool:
        return self.target_id == self.self_id

    @override
    def get_user_id(self) -> str:
        return str(self.target_id)


class GroupHonorNotifyEvent(NotifyEvent):
    """群成员荣誉变更"""

    __event__ = "notice.notify.honor"
    sub_type: Literal["honor"]
    group_id: int
    honor_type: Literal["talkative", "performer", "emotion"]

    @override
    def is_tome(self) -> bool:
        return self.user_id == self.self_id


class RequestEvent(CQHTTPEvent):
    """请求事件"""

    __event__ = "request"
    post_type: Literal["request"]
    request_type: str

    @override
    def get_event_name(self) -> str:
        sub_type = getattr(self, "sub_type", None)
        return f"{self.post_type}.{self.request_type}" + (f".{sub_type}" if sub_type else "")

    @override
    def get_session_id(self) -> str:
        if group_id := getattr(self, "group_id", None):
            return f"group_{group_id}_{self.get_user_id()}"
        return self.get_user_id()

    async def approve(self) -> dict[str, Any]:
        """同意请求。

        Returns:
            API 请求响应。
        """
        raise NotImplementedError

    async def refuse(self) -> dict[str, Any]:
        """拒绝请求。

        Returns:
            API 请求响应。
        """
        raise NotImplementedError


class FriendRequestEvent(RequestEvent):
    """加好友请求"""

    __event__ = "request.friend"
    request_type: Literal["friend"]
    user_id: int
    comment: str
    flag: str

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)

    @override
    async def approve(self, remark: str = "") -> dict[str, Any]:
        """同意请求。

        Args:
            remark: 好友备注。

        Returns:
            API 请求响应。
        """
        return await self.adapter.set_friend_add_request(
            flag=self.flag, approve=True, remark=remark
        )

    @override
    async def refuse(self) -> dict[str, Any]:
        return await self.adapter.set_friend_add_request(flag=self.flag, approve=False)


class GroupRequestEvent(RequestEvent):
    """加群请求 / 邀请"""

    __event__ = "request.group"
    request_type: Literal["group"]
    sub_type: Literal["add", "invite"]
    group_id: int
    user_id: int
    comment: str
    flag: str

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)

    @override
    async def approve(self) -> dict[str, Any]:
        return await self.adapter.set_group_add_request(
            flag=self.flag, sub_type=self.sub_type, approve=True
        )

    @override
    async def refuse(self, reason: str = "") -> dict[str, Any]:
        """拒绝请求。

        Args:
            reason: 拒绝原因。

        Returns:
            API 请求响应。
        """
        return await self.adapter.set_group_add_request(
            flag=self.flag, sub_type=self.sub_type, approve=False, reason=reason
        )


class MetaEvent(CQHTTPEvent):
    """元事件"""

    __event__ = "meta_event"
    post_type: Literal["meta_event"]
    meta_event_type: str


class LifecycleMetaEvent(MetaEvent):
    """生命周期"""

    __event__ = "meta_event.lifecycle"
    meta_event_type: Literal["lifecycle"]
    sub_type: Literal["enable", "disable", "connect"]


class HeartbeatMetaEvent(MetaEvent):
    """心跳"""

    __event__ = "meta_event.heartbeat"
    meta_event_type: Literal["heartbeat"]
    status: Status
    interval: int
