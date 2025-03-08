from sekaibot import Node
from sekaibot.rule import rule_at_me

@rule_at_me
class HelloWorldNode(Node):
    """Hello, World! 示例节点。"""
    