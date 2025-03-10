from sekaibot import Node
#from sekaibot.rule import rule_at_me

#@rule_at_me
class HelloWorldNode(Node):
    """Hello, World! 示例节点。"""
    priority = 0
    async def handle(self):
        return None
    
    
class HelloWorldNode1(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode"
    priority = 5
    async def handle(self):
        return None
    
    async def rule(self):
        return True
    
class HelloWorldNode2(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode"
    priority = 2
    async def handle(self):
        pass
    
    async def rule(self):
        return True
    
class HelloWorldNode1_1(Node):
    """Hello, World! 示例节点。"""
    parent = "HelloWorldNode1"
    priority = 5
    async def handle(self):
        return None
    
    async def rule(self):
        return True
    

    