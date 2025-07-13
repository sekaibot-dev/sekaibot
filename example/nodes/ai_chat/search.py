import os
import re
import warnings
from contextlib import suppress
from http import HTTPStatus

import anyio
import dashscope  # type: ignore
from bs4 import GuessedAtParserWarning
from duckduckgo_search import DDGS
from langchain.text_splitter import SpacyTextSplitter
from langchain.tools import tool
from langchain_community.document_loaders import WikipediaLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from zhconv import convert  # type: ignore

from example.nodes.ai_chat.agent import create_agent, create_embeddings, faiss_service
from example.nodes.ai_chat.moegirl import MoegirlLoader
from example.nodes.ai_chat.prompt import search_prompt

# 设置全局 HTTP/HTTPS 代理
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"

warnings.filterwarnings("ignore", category=GuessedAtParserWarning)
text_splitter = SpacyTextSplitter(
    chunk_size=200,
    pipeline="zh_core_web_sm",
    chunk_overlap=20,
)

embeddings = create_embeddings()  # "text-embedding-v3", provider="DASHSCOPE"

SIMILARITY_THRESHOLD = 0.75
MIN_CONTENT_LEN = 20


def text_rerank(query: str, documents: list[str], top_n: int = 10) -> str | None:
    resp = dashscope.TextReRank.call(
        model="gte-rerank-v2",
        query=query,
        documents=documents,
        top_n=top_n,
        return_documents=False,
    )
    if resp.status_code == HTTPStatus.OK:
        return "。".join(documents[r.index] for r in resp.output.results) + "。"
    return None


async def asimilarity_search(
    db: FAISS, keyw: str, query: str, top_n: int = 3
) -> str | None:
    results_with_scores = await db.asimilarity_search_with_score(
        query=query, k=top_n, filter={"title": keyw}
    )
    print(results_with_scores)
    results = [
        doc for doc, score in results_with_scores if score < SIMILARITY_THRESHOLD
    ]
    if results:
        return re.sub(r"\n+", "\n", "\n".join(doc.page_content for doc in results))
    return None


@tool(
    description='使用维基百科搜索具体词条，例如人物、概念或组织。查询必须包含明确关键词，否则可能无结果。keyw 是具体词条关键词，query 是查询内容（尽量较完整，不需要复述 keyw）。top_n 指定返回的句子数，最多10，top_n 越大返回越慢，默认为3。如 keyw="初音未来"，query="最著名的歌"，top_n=3。结果准确，但可能失败或无效。'
)
async def wiki_search(keyw: str, query: str, top_n: int = 3) -> str | None:
    keyw, query = convert(keyw, "zh-cn"), convert(query, "zh-cn")
    with (
        suppress(Exception),
        faiss_service("../sekaibot-cache/wiki", embeddings) as db,
    ):
        if result := await asimilarity_search(db, keyw, query, top_n):
            return result

        loader = WikipediaLoader(keyw, lang="zh", load_max_docs=1)
        docs = text_splitter.split_documents(
            [
                Document(
                    page_content=convert(doc.page_content, "zh-cn"),
                    metadata={k: convert(v, "zh-cn") for k, v in doc.metadata.items()},
                )
                for doc in await loader.aload()
            ]
        )
        docs = [
            doc
            for doc in docs.copy()
            if not (
                exist := await db.asimilarity_search_with_score(
                    doc.page_content, k=1, filter={"title": keyw}
                )
            )
            or exist[0][1] >= SIMILARITY_THRESHOLD
        ]
        if docs:
            await db.aadd_documents(docs)
            return await asimilarity_search(db, keyw, query, top_n)
    return None


@tool(
    description='使用萌娘百科搜索具体词条，擅长二次元人物、VOCALOAD人物、VOCALOAD P主、动漫、动漫角色、动漫梗、虚拟主播（vtuber）、虚拟歌姬等泛ACG内容查询。查询必须包含明确关键词，否则可能无结果。keyw 是具体词条关键词，query 是查询内容（尽量较完整，不需要复述 keyw）。top_n 指定返回的句子数，最多10，top_n 越大返回越慢，默认为3。如 keyw="初音未来"，query="最著名的歌"，top_n=3。结果准确，但可能失败或无效。'
)
async def moegirl_search(keyw: str, query: str, top_n: int = 3) -> str | None:
    keyw, query = convert(keyw, "zh-cn"), convert(query, "zh-cn")
    print(keyw, query)
    with (
        suppress(Exception),
        faiss_service("../sekaibot-cache/moegirl", embeddings) as db,
    ):
        if result := await asimilarity_search(db, keyw, query, top_n):
            return result

        loader = MoegirlLoader(keyw)
        docs = text_splitter.split_documents(
            [
                Document(
                    page_content=convert(doc.page_content, "zh-cn"),
                    metadata={k: convert(v, "zh-cn") for k, v in doc.metadata.items()},
                )
                for doc in await loader.aload()
            ]
        )
        docs = [
            doc
            for doc in docs.copy()
            if not (
                exist := await db.asimilarity_search_with_score(
                    doc.page_content, k=1, filter={"title": keyw}
                )
            )
            or exist[0][1] >= SIMILARITY_THRESHOLD
        ]
        if docs:
            await db.aadd_documents(docs)
            return await asimilarity_search(db, keyw, query, top_n)
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
    tools=[moegirl_search, wiki_search, web_search],
    strict=True,
    verbose=True,
)


@tool(
    description="自动根据问题类型调用维基百科或网页搜索，支持多轮尝试、结果优化与简体中文输出，内置失败兜底逻辑。遇到不明确的问题请尝试"
)
async def search_tool(query: str) -> str | None:
    if result := await search_model.ainvoke({"input": f"query: {query}"}):
        return result.get("output", None).replace("\n", " ").replace("\r", "").strip()
    return None


async def main():
    # print(await wiki_search.ainvoke({"keyw": "若叶睦", "query": "若叶睦"}))
    # print(await moegirl_search.ainvoke({"keyw": "若叶睦", "query": "性格"}))
    import time

    print(t1 := time.time())
    print(
        await moegirl_search.ainvoke({"keyw": "丰川祥子", "query": "性格"})
    )  # print(await search_tool.ainvoke({"query": "丰川祥子 性格"}))
    print(time.time() - t1)


if __name__ == "__main__":
    anyio.run(main)
