from sekaibot.config import ConfigModel


class RuleConfig(ConfigModel):
    command_start: str
    command_sep: str
