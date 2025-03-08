# core/memory_manager.py

import asyncio
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage
from typing import Literal, Dict, Any, List
from .utils import cacheDict

class MemoryManager:
    """
    使用 RedisChatMessageHistory 管理持久化的对话记忆。
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "chat_history",
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        # 用于缓存 session_id -> RedisChatMessageHistory 实例
        self._history_cache: cacheDict[str, RedisChatMessageHistory] = cacheDict(max_size=50)

    def get_history(
        self, session_id: str
    ) -> RedisChatMessageHistory:
        """
        获取指定 session_id 的 RedisChatMessageHistory 对象，若无则创建。
        """
        if session_id not in self._history_cache:
            self._history_cache[session_id] = RedisChatMessageHistory(
                url=self.redis_url,
                session_id=session_id,
                key_prefix=self.key_prefix
            )
        return self._history_cache[session_id]

    async def add_message(self, session_id: str, role: Literal["user", "assistant", "system"], content: str, timestamp: int = None, message_id: str = None):
        """优化消息存储逻辑"""
        history = self.get_history(session_id)
        
        msg = HumanMessage(content=content, additional_kwargs={"timestamp": timestamp, "message_id": message_id}) if role == "user" else \
            AIMessage(content=content, additional_kwargs={"timestamp": timestamp, "message_id": message_id}) if role == "assistant" else \
            SystemMessage(content=content, additional_kwargs={"timestamp": timestamp, "message_id": message_id}) if role == "system" else None
        if msg is not None:
            await history.aadd_messages([msg])  # 直接使用异步方法

    async def add_messages(
        self,
        session_id: str,
        messages: List[Dict[str, Any]]
    ) -> None:
        history = self.get_history(session_id)
        msg_list = [
            HumanMessage(content=message.get("content"), additional_kwargs={"timestamp": message.get("timestamp"),"message_id": message.get("message_id"),}) if message.get("role") == "user" else \
            AIMessage(content=message.get("content"), additional_kwargs={"timestamp": message.get("timestamp"),"message_id": message.get("message_id"),}) if message.get("role") == "assistant" else \
            SystemMessage(content=message.get("content"), additional_kwargs={"timestamp": message.get("timestamp"),"message_id": message.get("message_id"),}) if message.get("role") == "system" else None
            for message in messages
        ]
        await history.aadd_messages(list(filter(lambda x: x is not None, msg_list)))

    async def load_messages(
        self, session_id: str
    ) -> List[BaseMessage]:
        """
        加载指定 session_id 的完整消息列表。
        返回 langchain.schema.BaseMessage 列表。
        """
        history = self.get_history(session_id)
        return await history.aget_messages()
    
    async def clear_messages(
        self, session_id: str
    ):
        history = self.get_history(session_id)
        await history.aclear()
