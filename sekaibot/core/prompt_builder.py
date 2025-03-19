# core/prompt_builder.py
from config import Config
from langchain.schema import SystemMessage, HumanMessage, AIMessage, BaseMessage
from datetime import datetime
from typing import List, Dict, TYPE_CHECKING
from functools import cached_property
if TYPE_CHECKING:
    from ..bot import Bot

class PromptBuilder: 
    bot: "Bot"

    def __init__(self, bot: "Bot"):
        self.bot = bot
        self.role_definition = self.bot.config.role_definition
        self.symbol_conversation = self.bot.config.symbol_conversation

    @cached_property
    def basic_settings(
        self,
    ) -> list[BaseMessage]:
        """
        构建系统消息，包含角色设定和用户资料等。
        返回一个包含 SystemMessage 的列表，供每次调用时放在对话最前面。
        """


        role_msg = [SystemMessage(content=self.role_definition)]
        symbol_msg = [
            SystemMessage(content="以下是样例对话"),
            *(
                msg
                for convo in self.symbol_conversation
                for msg in (HumanMessage(content=convo["input"]), AIMessage(content=convo["output"]))
            ),
            SystemMessage(content="以上是样例对话"),
        ] if self.symbol_conversation is not None and len(self.symbol_conversation) > 0 else []
        
        return role_msg + symbol_msg
    
    def get_system_message(
        self, user_name: str
    ) -> list[BaseMessage]:
        """
        获取包含系统消息的列表
        """
        now_str = datetime.now().strftime("%Y年%m月%d日 %H点%M分")
        info_msg = [SystemMessage(content=(
            f"当前时间：{now_str}\n"
            f"对方名称：{user_name}\n"
        ))]

        return self.basic_settings + info_msg