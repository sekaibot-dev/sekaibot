import asyncio
from typing import Optional

from config import Config
from utils import check_group_keywords, is_at_bot, is_private_message
from core.agent_executor import ChatAgentExecutor

class Bot():

    def __init__(self, config: Config):
        self.config = config
        self.chat_agent = ChatAgentExecutor(
            bot=self,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model_name=self.config.model,
            redis_url=self.config.redis_url
        )
        

    def get_session_id(self, event: dict):
        if is_private_message(event):
            return "user_" + str(event.get("user_id"))
        else:
            return "group_" + str(event.get("group_id"))

    def check_answer(self, event: dict) -> bool:
        
        if is_private_message(event):
            return True
        is_group = (event.get("message_type") == "group")
        group_keywords_hit = False
        if is_group:
            group_keywords_hit = check_group_keywords(event.get("plain_text", ""), self.config.keywords)
        return is_at_bot(event) or (is_group and group_keywords_hit)
        
        

    async def handle_message(self, event: dict) -> Optional[str]:
        """
        核心消息处理入口：
        1. 判断是否需要回复：
        - 私聊 or (群聊且 at_bot==True) or (群聊且命中关键词)
        2. 如果需要回复，调用 LangChain Agent 获取回复并返回。
        3. 如果不需要回复，仅做消息存储，返回 None。
        """
        session_id = self.get_session_id(event)
        
        if not self.check_answer(event):
            await self.chat_agent.memory_manager.add_message(
                session_id=session_id,
                role="user",
                input=event.get("plain_text"),
                timestamp=int(event.get("time")),
                message_id=str(event.get("message_id"))
            )
            return None
        
        reply = (await self.chat_agent.run(
            message=event, 
            session_id=session_id,
            timestamp=int(event.get("time")),
            message_id=str(event.get("message_id")), 
        ))

        return reply

    

if __name__ == "__main__":
    # 示例：模拟私聊测试
    sample_event_private = {
        "type": "message",
        "time": 1738559871,
        "self_id": 3988189771,
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": 24495503,
        "user_id": 2122331,
        "plain_text": "我是谁",
        "user_name": "Miku",
        "ask_bot": True,
        "startwith_atbot": False
    }

    # 示例：模拟群聊测试
    sample_event_group = {
        "type": "message",
        "time": 1738559959,
        "self_id": 3988189771,
        "post_type": "message",
        "message_type": "group",
        "group_id": 89411261,
        "message_id": 1593257552,
        "user_id": 26820646331,
        "plain_text": "我叫什么名字",
        "user_name": "Miku",
        "ask_bot": False,
        "startwith_atbot": True
    }
    bot = Bot(Config())

    async def run_test():
        resp1 = await bot.handle_message(sample_event_private)
        print("私聊回复:", resp1)

        resp2 = await bot.handle_message(sample_event_group)
        print("群聊回复:", resp2)

    asyncio.run(run_test())
