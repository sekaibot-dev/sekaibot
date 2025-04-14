"""SekaiBot 权限控制"""

from typing import Any

from sekaibot.internal.permission import Permission, PermissionChecker
from sekaibot.internal.permission.utils import SuperUserPermission, UserPermission

__all__ = ["User", "SuperUser", "SuperUserPermission", "UserPermission"]


class User(PermissionChecker[tuple[tuple[str, ...], Permission]]):
    """匹配当前事件属于指定会话。

    如果 `perm` 中仅有 `User` 类型的权限检查函数，则会去除原有检查函数的会话 ID 限制。

    Args:
        users: 白名单会话 ID 元组。
               - 用户 ID 为纯字符串，例如 `"123456"`
               - 群聊 ID 需添加前缀，例如 `"group_654321"`
               - 精准会话 ID 格式为：`"group_<群聊ID>_<用户ID>"`
        strict: 是否严格匹配会话 ID。
                - 若为 `True`，则只匹配完全一致的会话 ID（如某群的某个用户）
                - 若为 `False`，则允许包含匹配：
                  用户 ID 可匹配私聊和群聊
                  群聊 ID（以 `"group_"` 开头）仅匹配群聊
        perm: 需要同时满足的权限

    """

    def __init__(self, *users: str, strict: bool, perm: Permission | None = None):
        super().__init__(
            Permission(UserPermission.from_permission(*users, strict=strict, perm=perm))
        )

    @classmethod
    def Checker(cls, *users: str, strict: bool, perm: Permission | None = None):
        return super().Checker(*users, strict=strict, perm=perm)


class SuperUser(PermissionChecker[Any]):
    """检查当前事件是否是消息事件且属于超级管理员"""

    def __init__(self):
        super().__init__(Permission(SuperUserPermission()))

    @classmethod
    def Checker(cls):
        return super().Checker()
