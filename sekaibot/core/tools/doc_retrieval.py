from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS, Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.document_loaders import TextLoader, UnstructuredImageLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from typing import TYPE_CHECKING, List, Optional
import os

from .utils import BaseTool

if TYPE_CHECKING:
    from ...bot import Bot

class DocumentRetrievalTool(BaseTool):
    """
    文档检索工具，支持 RAG 机制和多模态文件输入（文本、PDF、图片）。
    使用 LangChain 最新 API，包括新版向量库、嵌入模型和检索链。
    """

    def __init__(
        self,
        bot: "Bot",
        name: str, 
        description: str,
        *,
        vector_store: str = "faiss",
        embedding_model: str = "openai",
        model_name: str = "gpt-3.5-turbo",
    ) -> None:
        """
        初始化文档检索工具。

        :param vector_store: 选择使用的向量数据库，支持 "faiss" 或 "chroma"
        :param embedding_model: 选择使用的嵌入模型，目前支持 "openai" 和 "huggingface"
        :param model_name: 选择的 LLM 模型名称（新版 ChatOpenAI 位于 langchain_openai 模块）
        """
        super().__init__(
            bot=bot,
            name=name,
            description=description,
        )

        # 选择嵌入模型
        if embedding_model == "openai":
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=self.bot.config.api_key,
                base_url=self.bot.config.base_url,
            )
        elif embedding_model == "huggingface":
            self.embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
        else:
            raise ValueError("不支持的 embedding 模型！")

        self.vector_store_type: str = vector_store
        self.db: Optional[FAISS | Chroma] = None  # 初始时尚未添加文档

        # 初始化 LLM（新版 ChatOpenAI）
        self.llm = ChatOpenAI(
            openai_api_key=self.bot.config.api_key,
            base_url=self.bot.config.base_url,
            model=model_name,
        )

    def _load_documents(self, file_paths: List[str]) -> List[Document]:
        """
        加载文档，支持文本和图片格式。

        :param file_paths: 文件路径列表
        :return: 分块后的 Document 列表
        """
        documents: List[Document] = []
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

        for file_path in file_paths:
            ext = os.path.splitext(file_path)[-1].lower()
            if ext == ".txt":
                loader = TextLoader(file_path)
            elif ext in [".jpg", ".png"]:
                loader = UnstructuredImageLoader(file_path)
            else:
                raise ValueError(f"不支持的文件格式：{ext}")

            docs = loader.load()
            split_docs = text_splitter.split_documents(docs)
            documents.extend(split_docs)

        return documents

    def add_documents(self, file_paths: List[str]) -> None:
        """
        添加文档至向量数据库。

        :param file_paths: 文件路径列表
        """
        new_docs = self._load_documents(file_paths)
        if not new_docs:
            return

        if self.db is None:
            # 初始化向量数据库
            if self.vector_store_type == "faiss":
                self.db = FAISS.from_documents(new_docs, self.embeddings)
            elif self.vector_store_type == "chroma":
                self.db = Chroma.from_documents(
                    new_docs, self.embeddings, collection_name="document_retrieval"
                )
            else:
                raise ValueError("不支持的向量数据库类型！")
        else:
            self.db.add_documents(new_docs)

    def _retrieve_doc(self, query: str) -> str:
        """
        使用 RAG 机制检索文档并生成答案。

        :param query: 用户查询
        :return: 基于上下文生成的回答
        """
        if self.db is None:
            return "未添加任何文档，请先调用 add_documents 方法添加文档。"

        # 定义回答时使用的 Prompt 模板
        system_prompt = (
            "Use the given context to answer the question. "
            "If you don't know the answer, say you don't know. "
            "Use three sentence maximum and keep the answer concise. "
            "Context: {context}"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        # 创建检索链
        question_answer_chain = create_stuff_documents_chain(self.llm, prompt)
        qa_chain = create_retrieval_chain(
            self.db.as_retriever(), question_answer_chain
        )
        return qa_chain.invoke({"input": query})

    def run(self, query: str) -> str:
        """
        主接口，接收查询文本并返回检索生成的回答。

        :param query: 用户查询
        :return: 回答文本
        """
        return self._retrieve_doc(query)


# 初始化工具
retrieval_tool = DocumentRetrievalTool(vector_store="faiss", embedding_model="openai")

# 添加文档
retrieval_tool.add_documents(["D:/QQBot/chatbot/core/tools/sample.txt"])

# 进行查询
query_result = retrieval_tool.run("请问这个文档讲了什么？")
print(query_result)
