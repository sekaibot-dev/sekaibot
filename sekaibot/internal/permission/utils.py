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

from sekaibot.internal.adapter import Adapter
from sekaibot.internal.event import Event
from sekaibot.internal.permission import Permission as Permission
from sekaibot.typing import GlobalStateT

if TYPE_CHECKING:
    from sekaibot.bot import Bot


class UserPermission:
    """检查当前事件是否属于指定会话。

    参数:
        users: 会话 ID 元组
        perm: 需同时满足的权限
    """

    __slots__ = ("perm", "users")

    def __init__(self, users: tuple[str, ...], perm: Permission | None = None) -> None:
        self.users = users
        self.perm = perm

    def __repr__(self) -> str:
        return (
            f"User(users={self.users}" + (f", permission={self.perm})" if self.perm else "") + ")"
        )

    async def __call__(self, bot: "Bot", event: Event, global_state: GlobalStateT) -> bool:
        try:
            session = event.get_session_id()
        except Exception:
            return False
        return bool(
            session in self.users
            and (self.perm is None or await self.perm(bot, event, global_state))
        )

    @classmethod
    def _clean_permission(cls, perm: Permission) -> Permission | None:
        if len(perm.checkers) == 1 and isinstance(user_perm := next(iter(perm.checkers)).call, cls):
            return user_perm.perm
        return perm

    @classmethod
    def from_event(cls, event: Event, perm: Permission | None = None) -> Self:
        """从事件中获取会话 ID。

        如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有的会话 ID 限制。

        参数:
            event: Event 对象
            perm: 需同时满足的权限
        """
        return cls((event.get_session_id(),), perm=perm and cls._clean_permission(perm))

    @classmethod
    def from_permission(cls, *users: str, perm: Permission | None = None) -> Self:
        """指定会话与权限。

        如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有的会话 ID 限制。

        参数:
            users: 会话白名单
            perm: 需同时满足的权限
        """
        return cls(users, perm=perm and cls._clean_permission(perm))


def USER(*users: str, perm: Permission | None = None):
    """匹配当前事件属于指定会话。

    如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有检查函数的会话 ID 限制。

    参数:
        user: 会话白名单
        perm: 需要同时满足的权限
    """

    return Permission(UserPermission.from_permission(*users, perm=perm))


class SuperUserPermission:
    """检查当前事件是否是消息事件且属于超级管理员"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Superuser()"

    async def __call__(self, bot: "Bot", event: Event[Adapter[Any, Any]]) -> bool:
        try:
            user_id = event.get_user_id()
        except Exception:
            return False
        return (
            f"{event.adapter.name.split(maxsplit=1)[0].lower()}:{user_id}"
            in bot.config.bot.superusers
            or user_id in bot.config.bot.superusers  # 兼容旧配置
        )


__autodoc__ = {
    "Permission": True,
    "Permission.__call__": True,
    "User": True,
    "USER": True,
}
