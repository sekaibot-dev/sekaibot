import asyncio
from typing import List, Dict, Any, Optional, Type, TYPE_CHECKING
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.agents.agent_types import AgentType
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from .tools import get_tools  # 确保工具模块已实现function calling格式
from .memory_manager import MemoryManager
from .prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from ..bot import Bot

class Models():
    """多种llm模型的整合端口"""
    bot: "Bot"

    def __init__(
        self,
        bot: "Bot"
    ):
        self.bot = bot