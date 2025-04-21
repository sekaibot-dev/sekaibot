"""SekaiBot 权限控制"""

from typing_extensions import override

from sekaibot.internal.permission import Permission, PermissionChecker
from sekaibot.internal.permission.utils import SuperUserPermission, UserPermission

__all__ = ["SuperUser", "SuperUserPermission", "User", "UserPermission"]


class User(PermissionChecker):
    """匹配当前事件属于指定会话。

    如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有检查函数的会话 ID 限制。

    Args:
        users: 白名单会话 ID 元组。
               - 用户 ID 为纯字符串，例如 `"123456"`
               - 群聊 ID 需添加前缀，例如 `"group_654321"`
               - 精准会话 ID 格式为：`"group_<群聊ID>_<用户ID>"`
        perm: 需要同时满足的权限

    """

    def __init__(self, *users: str, perm: Permission | None = None) -> None:
        super().__init__(Permission(UserPermission.from_permission(users, perm=perm)))

    @override
    @classmethod
    def Checker(cls, *users: str, perm: Permission | None = None) -> bool:
        """匹配当前事件属于指定会话。

        Args:
            users: 白名单会话 ID 元组。
                - 用户 ID 为纯字符串，例如 `"123456"`
                - 群聊 ID 需添加前缀，例如 `"group_654321"`
                - 精准会话 ID 格式为：`"group_<群聊ID>_<用户ID>"`
            perm: 需要同时满足的权限
        """
        return super().Checker(users, perm=perm)


class SuperUser(PermissionChecker):
    """检查当前事件是否是消息事件且属于超级管理员"""

    def __init__(self) -> None:
        super().__init__(Permission(SuperUserPermission()))

    @override
    @classmethod
    def Checker(cls) -> bool:
        """检查当前事件是否是消息事件且属于超级管理员"""
        return super().Checker()
