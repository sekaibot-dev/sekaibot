# core/tools/__init__.py

from typing import List
from langchain.agents import Tool
from .web_search import WebSearchTool
from .doc_retrieval import DocumentRetrievalTool


def get_tools() -> list[Tool]:
    """
    返回可用的 Tool 列表。
    你可以在这里收集所有需要暴露给 Agent 的工具。
    """
    return [
        WebSearchTool().to_tool(),
        DocumentRetrievalTool().to_tool(),
    ]
