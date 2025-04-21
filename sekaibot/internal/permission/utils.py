"""本模块是 {ref}`nonebot.matcher.Matcher.permission` 的类型定义。

每个{ref}`事件响应器 <nonebot.matcher.Matcher>`
拥有一个 {ref}`nonebot.permission.Permission`，其中是 `PermissionChecker` 的集合。
只要有一个 `PermissionChecker` 检查结果为 `True` 时就会继续运行。

FrontMatter:
    mdx:
        format: md
    sidebar_position: 6
    description: nonebot.permission 模块
"""

from typing import TYPE_CHECKING, Any, Self
from typing_extensions import override

from sekaibot.internal.event import Event
from sekaibot.internal.permission import Permission

if TYPE_CHECKING:
    from sekaibot.bot import Bot


class UserPermission:
    """检查当前事件是否属于指定会话。

    Args:
        users: 会话 ID 元组。
               - 用户 ID 为纯字符串，例如 `"123456"`
               - 群聊 ID 需添加前缀，例如 `"group_654321"`
               - 精准会话 ID 格式为：`"group_<群聊ID>_<用户ID>"`
        perm: 要求用户需同时满足的权限
    """

    __slots__ = ("perm", "users")

    def __init__(self, users: tuple[str, ...], perm: Permission | None = None) -> None:
        self.users = users
        self.perm = perm

    @override
    def __repr__(self) -> str:
        return (
            f"User(users={self.users}"
            + (f", permission={self.perm})" if self.perm else "")
            + ")"
        )

    async def __call__(self, event: Event[Any]) -> bool:
        """运行权限检测"""
        try:
            session = event.get_session_id()
        except Exception:
            return False
        return any(user in session for user in self.users)

    @classmethod
    def _clean_permission(cls, perm: Permission) -> Permission | None:
        if len(perm.checkers) == 1 and isinstance(
            user_perm := next(iter(perm.checkers)).call, cls # type: ignore
        ):
            return user_perm.perm
        return perm

    @classmethod
    def from_event(cls, event: Event[Any], perm: Permission | None = None) -> Self:
        """从事件中获取会话 ID。

        如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有的会话 ID 限制。

        Args:
            event: Event 对象
            perm: 需同时满足的权限
        """
        return cls((event.get_session_id(),), perm=perm and cls._clean_permission(perm))

    @classmethod
    def from_permission(
        cls, users: tuple[str, ...], perm: Permission | None = None
    ) -> Self:
        """指定会话与权限。

        如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有的会话 ID 限制。

        Args:
            users: 会话白名单
            perm: 需同时满足的权限
        """
        return cls(users, perm=perm and cls._clean_permission(perm))


class SuperUserPermission:
    """检查当前事件是否是消息事件且属于超级管理员"""

    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return "Superuser()"

    async def __call__(self, bot: "Bot", event: Event[Any]) -> bool:
        """运行超级用户检测"""
        try:
            user_id = event.get_user_id()
            group_id = (
                "group_" + str(getattr(event, "group_id", "no_group_id"))
            )
        except Exception:
            return False

        adapter_name = event.adapter.name.split(maxsplit=1)[0].lower()
        superusers = bot.config.permission.superusers
        return (
            f"{adapter_name}:{user_id}" in superusers
            or user_id in superusers  # 兼容旧配置
            or (
                (
                    f"{adapter_name}:{group_id}" in superusers
                    or group_id in superusers  # 兼容旧配置
                    or f"{adapter_name}:{group_id}_{user_id}" in superusers
                    or f"{group_id}_{user_id}" in superusers  # 兼容旧配置
                )
                if group_id
                else False
            )
        )


__autodoc__ = {
    "Permission": True,
    "Permission.__call__": True,
    "User": True,
    "USER": True,
}
