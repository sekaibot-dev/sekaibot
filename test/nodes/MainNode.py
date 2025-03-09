from sekaibot import Node
#from sekaibot.rule import rule_at_me

#@rule_at_me
class HelloWorldNode(Node):
    """Hello, World! 示例节点。"""
    priority = 0
    def handle(self):
        return None
    
    
class HelloWorldNode1(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode"
    priority = 5
    def handle(self):
        return None
    
    def rule(self):
        return True
    
class HelloWorldNode2(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode"
    priority = 2
    def handle(self):
        return None
    
    def rule(self):
        return True
    
class HelloWorldNode1_1(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode1"
    priority = 5
    def handle(self):
        return None
    
    def rule(self):
        return True
    
class HelloWorldNode2_1(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode1"
    priority = 2
    def handle(self):
        return None
    
    def rule(self):
        return True
    
class HelloWorldNode1_2(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode2"
    priority = 1
    def handle(self):
        return None
    
    def rule(self):
        return True
    
class HelloWorldNode2_2(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode2"
    priority = 2
    def handle(self):
        return None
    
    def rule(self):
        return True
    