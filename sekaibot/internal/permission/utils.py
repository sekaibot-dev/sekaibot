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

from sekaibot.bot import Bot
from sekaibot.internal.event import Event
from sekaibot.internal.permission import USER as USER
from sekaibot.internal.permission import Permission as Permission
from sekaibot.internal.permission import User as User


class SuperUser:
    """检查当前事件是否是消息事件且属于超级管理员"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Superuser()"

    async def __call__(self, bot: Bot, event: Event) -> bool:
        try:
            user_id = event.get_user_id()
        except Exception:
            return False
        return (
            f"{bot.adapter.name.split(maxsplit=1)[0].lower()}:{user_id}"
            in bot.config.superusers
            or user_id in bot.config.superusers  # 兼容旧配置
        )


SUPERUSER: Permission = Permission(SuperUser())
"""匹配任意超级用户事件"""

__autodoc__ = {
    "Permission": True,
    "Permission.__call__": True,
    "User": True,
    "USER": True,
}
