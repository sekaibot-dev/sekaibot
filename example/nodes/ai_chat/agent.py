from typing import Literal

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate
from langchain.tools import BaseTool
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.utils import secret_from_env, from_env
from langchain_openai import ChatOpenAI

from .history import ChatMessageHistory

histories: dict[str, ChatMessageHistory] = {}


def get_session_history(session_id: str) -> ChatMessageHistory:
    """根据 session_id 返回一个 BaseChatMessageHistory 实例，

    这里用内存或文件存储两种示例，你可任选其一或自行替换为 RedisChatMessageHistory、数据库等。
    """
    if session_id not in histories:
        histories[session_id] = ChatMessageHistory(
            file_path=f"../sekaibot-cache/history_{session_id}.json",
            max_len=24,
        )
    return histories[session_id]


def create_agent(
    model: str,
    *,
    provider: Literal["OPENAI", "DASHSCOPE"],
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
        base_url=from_env(f"{provider}_BASE_URL")(),
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
    provider: Literal["OPENAI", "DASHSCOPE"],
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
        input_messages_key="messages",  # 输入字典里存用户最新一条消息的 key
    )


async def clear(session_id: str) -> None:
    await get_session_history(session_id).aclear()
