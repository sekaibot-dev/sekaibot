from typing import Literal

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate
from langchain.tools import BaseTool
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.utils import from_env, secret_from_env
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .history import ChatMessageHistory

histories: dict[str, ChatMessageHistory] = {}


def get_session_history(session_id: str) -> ChatMessageHistory:
    """根据 session_id 返回一个 BaseChatMessageHistory 实例，

    这里用内存或文件存储两种示例，你可任选其一或自行替换为 RedisChatMessageHistory、数据库等。
    """
    if session_id not in histories:
        histories[session_id] = ChatMessageHistory(
            file_path=f"../sekaibot-cache/history_{session_id}.json",
            max_len=40,
        )
    return histories[session_id]


def create_agent(
    model: str,
    *,
    provider: Literal["OPENAI", "DASHSCOPE", "DEEPSEEK"],
    prompt: ChatPromptTemplate,
    temperature: float = 1,
    tools: list[BaseTool] | None = None,
    strict: bool = False,
    verbose: bool = False,
) -> AgentExecutor:
    llm = ChatOpenAI(
        model=model,
        api_key=secret_from_env(f"{provider}_API_KEY")(),
        temperature=temperature,
        base_url=from_env(f"{provider}_API_BASE")(),
    )
    tools = tools if tools else []
    agent = create_openai_tools_agent(
        llm=llm, tools=tools, prompt=prompt, strict=strict
    )
    return AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=tools,
        verbose=verbose,
    )


def create_agent_with_history(
    model: str,
    *,
    provider: Literal["OPENAI", "DASHSCOPE", "DEEPSEEK"],
    prompt: ChatPromptTemplate,
    temperature: float = 1,
    tools: list[BaseTool] | None = None,
    verbose: bool = False,
) -> RunnableWithMessageHistory:
    agent_executor = create_agent(
        model=model,
        provider=provider,
        prompt=prompt,
        temperature=temperature,
        tools=tools,
        verbose=verbose,
    )

    return RunnableWithMessageHistory(
        agent_executor,  # type: ignore
        get_session_history,
        input_messages_key="messages",
    )


def create_embeddings(
    model: str = "text-embedding-ada-002",
    *,
    provider: Literal["OPENAI", "DASHSCOPE"] = "OPENAI",
) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=model,
        api_key=secret_from_env(f"{provider}_API_KEY")(),
        base_url=from_env(f"{provider}_API_BASE")(),
    )


class FaissService:
    """Faiss上下文管理器"""

    def __init__(
        self, folder_path: str, embeddings: Embeddings, index_name: str = "index"
    ):
        self.folder_path = folder_path
        self.embeddings = embeddings
        self.index_name = index_name
        self.db = None

    def __enter__(self) -> FAISS:
        try:
            self.db = FAISS.load_local(
                folder_path=self.folder_path,
                embeddings=self.embeddings,
                index_name=self.index_name,
                allow_dangerous_deserialization=True,
            )
        except Exception:
            self.db = FAISS.from_texts(["空向量"], self.embeddings, ids=["dummy-id"])
            self.db.delete(ids=["dummy-id"])
        return self.db

    def __exit__(self, exc_type, exc_value, traceback):
        if self.db:
            self.db.save_local(folder_path=self.folder_path, index_name=self.index_name)


def faiss_service(
    folder_path: str, embeddings: Embeddings, index_name: str = "index"
) -> FaissService:
    return FaissService(folder_path, embeddings, index_name)


async def clear(session_id: str) -> None:
    await get_session_history(session_id).aclear()
