import os
import re
import warnings
from contextlib import suppress
from http import HTTPStatus

import dashscope  # type: ignore
from bs4 import GuessedAtParserWarning
from duckduckgo_search import DDGS
from langchain.tools import tool
from langchain_community.document_loaders import WikipediaLoader
from zhconv import convert  # type: ignore

from example.nodes.ai_chat.agent import create_agent
from example.nodes.ai_chat.prompt import search_prompt

# 设置全局 HTTP/HTTPS 代理
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"

warnings.filterwarnings("ignore", category=GuessedAtParserWarning)


def text_rerank(query: str, documents: list[str], top_n: int = 10) -> str | None:
    resp = dashscope.TextReRank.call(
        model="gte-rerank-v2",
        query=query,
        documents=documents,
        top_n=top_n,
        return_documents=False,
    )
    if resp.status_code == HTTPStatus.OK:
        return "。".join(documents[r.index] for r in resp.output.results)
    return None


@tool(
    description='使用维基百科搜索具体词条，例如人物、概念或组织。查询必须包含明确关键词，否则可能无结果。keyw 是具体词条关键词，query 是查询内容（尽量较完整，不需要复述 keyw）。top_n 指定返回的句子数，最多10，top_n 越大返回越慢，默认为3。如 keyw="初音未来"，query="最著名的歌"，top_n=3。结果准确，但可能失败或无效。'
)
def wiki_search(keyw: str, query: str, top_n: int = 3) -> str | None:
    with suppress(Exception):
        loader = WikipediaLoader(keyw, lang="zh", load_max_docs=1)
        docs = loader.load()
        doc_texts = [
            convert(sentence, "zh-cn")
            for doc in docs
            for sentence in re.split(
                r"[。．！？!.?]+",  # noqa: RUF001
                doc.page_content.replace("\n", ""),
            )
            if sentence.strip() and len(sentence) > 20  # noqa: PLR2004
        ]
        return text_rerank(query, doc_texts, top_n=top_n)
    return None


@tool(
    description="通过网页浏览器搜索，适用于查找任何类型的信息，包括模糊问题、最新事件或广泛主题。可以获得关于问题的简短回答。如果维基百科返回内容无效，请使用这个。top_n 指定返回的句子数，最多10，top_n 越大返回越慢，默认为3。"
)
def web_search(query: str, top_n: int = 3) -> str | None:
    with suppress(Exception), DDGS() as ddgs:
        results = ddgs.text(query, max_results=top_n * 3)
        doc_texts = [r["body"] for r in results]
        return convert(text_rerank(query, doc_texts, top_n=top_n), "zh-cn")
    return None


search_model = create_agent(
    "qwen-max",
    provider="DASHSCOPE",
    prompt=search_prompt,
    temperature=0.7,
    tools=[wiki_search, web_search],
    strict=True,
)


@tool(
    description="自动根据问题类型调用维基百科或网页搜索，支持多轮尝试、结果优化与简体中文输出，内置失败兜底逻辑。遇到不明确的问题请尝试"
)
def search_tool(query: str) -> str | None:
    if result := search_model.invoke({"input": f"query: {query}"}):
        return result.get("output", None)
    return None
