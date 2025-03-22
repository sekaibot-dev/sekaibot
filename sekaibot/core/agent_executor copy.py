import asyncio
from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI
from langchain.schema import BaseMessage, AIMessage, HumanMessage
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from .tools import get_tools


class ChatState(BaseModel):
    """
    维护对话状态，包括历史记录、当前输入、输出和其他元数据。
    """

    history: list[BaseMessage] = Field(default_factory=list)
    input: str = ""
    output: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)  # ✅ 允许存储 `user_id` 等额外信息


class ChatAgentExecutor:
    """
    基于 LangChain & OpenAI 的对话代理，支持高并发 & 动态工具管理
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "",
        model_name: str = "gpt-4-turbo",
        max_concurrency: int = 10,
    ):
        """
        初始化 LLM 代理，并构建对话流
        :param api_key: OpenAI API 密钥
        :param base_url: OpenAI 代理地址（可选）
        :param model_name: 使用的模型（默认 gpt-4-turbo）
        :param max_concurrency: 最大并发请求数
        """
        self.llm = ChatOpenAI(
            openai_api_key=api_key, base_url=base_url, model=model_name, temperature=0.7
        )
        self.graph = self._build_graph()

        self.semaphore = asyncio.Semaphore(max_concurrency)

    def _build_graph(self) -> StateGraph:
        """
        构建 LangGraph 对话流
        """
        graph = StateGraph(ChatState)
        graph.add_node("chat", self.run_chat)
        graph.set_entry_point("chat")
        return graph.compile()

    async def run_chat(self, state: ChatState) -> ChatState:
        """
        运行 LLM 处理完整对话上下文，并返回新的对话状态（兼容 `async`）。
        """
        messages = state.history + [HumanMessage(content=state.input)]  # ✅ 确保包含用户输入

        async with self.semaphore:  # ✅ 限制并发
            try:
                response: AIMessage = await self.llm.ainvoke(messages)  # ✅ 异步调用 OpenAI
                response_text: str = (
                    response.content if isinstance(response, AIMessage) else str(response)
                )
            except Exception as e:
                response_text = f"Error: {str(e)}"  # ✅ 避免崩溃，返回错误信息

        # ✅ 更新对话历史（追加用户输入 & AI 回复）
        new_history = state.history + [
            HumanMessage(content=state.input),
            AIMessage(content=response_text),
        ]

        return ChatState(history=new_history, output=response_text, metadata=state.metadata)

    async def run(
        self, messages: list[BaseMessage], metadata: dict[str, Any] | None = None
    ) -> ChatState:
        """
        执行 LangGraph 代理，返回完整对话状态（支持高并发）。
        """
        metadata = metadata or {}

        try:
            result = await self.graph.ainvoke(ChatState(history=messages, metadata=metadata))
            return result["output"]
        except Exception as e:
            return ChatState(history=messages, output=f"Error: {str(e)}", metadata=metadata)
