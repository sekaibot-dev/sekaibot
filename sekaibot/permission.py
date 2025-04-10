"""SekaiBot 权限控制"""

from typing import Any

from sekaibot.internal.permission import Permission, PermissionChecker
from sekaibot.internal.permission.utils import SuperUserPermission, UserPermission


class User(PermissionChecker[tuple[tuple[str, ...], Permission]]):
    """匹配当前事件属于指定会话。

    如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有检查函数的会话 ID 限制。

    Args:
        user: 会话白名单
        perm: 需要同时满足的权限
    """

    def __init__(self, *users: str, perm: Permission | None = None):
        super().__init__(Permission(UserPermission.from_permission(*users, perm=perm)))

    @classmethod
    def Checker(cls, *users: str, perm: Permission | None = None):
        return super().Checker(*users, perm=perm)


class SuperUser(PermissionChecker[Any]):
    """检查当前事件是否是消息事件且属于超级管理员"""

    def __init__(self):
        super().__init__(Permission(SuperUserPermission()))

    @classmethod
    def Checker(cls):
        return super().Checker()
