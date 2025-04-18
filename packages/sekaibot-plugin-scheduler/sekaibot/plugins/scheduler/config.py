from pydantic import Field

from sekaibot.config import ConfigModel


class SchedulerConfig(ConfigModel):
    """Scheduler 配置模型。
    Attributes:
        __config_name__: 配置名称。
        apscheduler_autostart: 是否自动启动调度器。
        apscheduler_log_level: APScheduler 日志级别。
        apscheduler_config: APScheduler 配置。
    """

    __config_name__: str = "scheduler"

    apscheduler_autostart: bool = True
    apscheduler_log_level: int = 30
    apscheduler_config: dict = Field(
        default_factory=lambda: {"apscheduler.timezone": "Asia/Shanghai"}
    )
