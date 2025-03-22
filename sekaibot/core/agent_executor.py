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


class ChatAgentExecutor:
    """支持OpenAI Function Calling的高性能异步代理"""

    bot: "Bot"
    llm: ChatOpenAI
    memory_manager: MemoryManager
    system_builder: PromptBuilder
    agent_executor: AgentExecutor

    def __init__(
        self,
        bot: "Bot",
        api_key: str,
        base_url: str = "",
        model_name: str = "gpt-4-turbo",
        redis_url: str = "",
    ):
        self.bot = bot
        self.llm = ChatOpenAI(
            openai_api_key=api_key, base_url=base_url, model=model_name, temperature=0.7
        )
        self.system_builder = PromptBuilder(self.bot)
        self.memory_manager = MemoryManager(redis_url=redis_url, key_prefix="chat_history")

        # 初始化带function calling的Agent
        self.agent_executor = self._build_agent_executor()

    def _build_agent_executor(self) -> AgentExecutor:
        """修正 `Prompt`，确保 `chat_history` 变量生效"""
        tools = get_tools()

        prompt = ChatPromptTemplate.from_messages(
            [
                MessagesPlaceholder(variable_name="system"),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        agent = create_openai_functions_agent(llm=self.llm, tools=tools, prompt=prompt)

        return AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=3)

    async def run_chat(
        self, system: list[BaseMessage], history: list[BaseMessage], input: str
    ) -> str:
        """优化 `AgentExecutor` 变量传递，确保历史记录正确传输"""
        async with asyncio.TaskGroup() as tg:
            history.append(HumanMessage(content=input))  # ✅ 追加用户输入

            task = tg.create_task(
                self.agent_executor.ainvoke(
                    {
                        "system": system,  # 传递完整系统消息
                        "input": input,  # 仅传入 `input` 字符串
                        "chat_history": history,  # 传递完整历史记录
                        "agent_scratchpad": [],  # 初始时为空，Agent 需要时自动填充
                    }
                )
            )
            response = await task
        return response["output"]

    async def run(
        self,
        message: dict,
        session_id: str,
        timestamp: int = None,
        message_id: str = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """执行完整对话流程"""
        metadata = metadata or {}
        input = message.get("plain_text")
        history = await self.memory_manager.load_messages(session_id)
        system = self.system_builder.get_system_message(message.get("user_name", "未知用户"))
        print(history)
        try:
            output = await self.run_chat(system, history, input)
            await self.memory_manager.add_message(session_id, "user", input, timestamp, message_id)
            await self.memory_manager.add_message(
                session_id, "assistant", output, timestamp, message_id
            )
            return output
        except Exception as e:
            raise e
