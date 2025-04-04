from pydantic import Field

from sekaibot.config import ConfigModel


class SchedulerConfig(ConfigModel):
    apscheduler_autostart: bool = True
    apscheduler_log_level: int = 30
    apscheduler_config: dict = Field(
        default_factory=lambda: {"apscheduler.timezone": "Asia/Shanghai"}
    )
