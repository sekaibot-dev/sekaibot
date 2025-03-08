from sekaibot.typing import EventT, NodeT
from sekaibot.utils import wrap_get_func

def _at_me(event: EventT):
    if event.message.startswith("@"):
        return True
    return False

def rule_at_me(cls: NodeT):
    cls.__node_rule_func__.append(wrap_get_func(_at_me))