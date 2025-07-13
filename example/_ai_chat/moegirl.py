from collections.abc import Iterator

import requests
from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document


class MoegirlLoader(BaseLoader):
    """萌娘百科文档加载器，输入词条名，返回正文 Document。参数设计兼容 WikipediaLoader。"""

    def __init__(
        self,
        query: str,
        lang: str = "zh",
        doc_content_chars_max: int | None = 4000,
    ):
        self.query = query
        self.doc_content_chars_max = doc_content_chars_max or 4000

        self.api_url = f"https://{lang}.moegirl.org.cn/api.php"

    def lazy_load(self) -> Iterator[Document]:
        """按词条名加载正文，返回 Document（可迭代）"""
        content = self._fetch_content(self.query)

        if content:
            # 限制正文长度
            if self.doc_content_chars_max:
                content = content[: self.doc_content_chars_max]

            metadata = {
                "source": "moegirl",
                "title": self.query,
            }

            yield Document(page_content=content, metadata=metadata)

    def _fetch_content(self, title: str) -> str | None:
        """通过 MediaWiki API 抓取正文内容"""
        params = {
            "action": "query",
            "prop": "extracts",
            "titles": title,
            "format": "json",
            "explaintext": True,
            "redirects": True,
        }

        try:
            response = requests.get(
                self.api_url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            pages = data.get("query", {}).get("pages", {})
            for page_data in pages.values():
                if "extract" in page_data:
                    return page_data["extract"]
        except Exception as e:
            print(f"[错误] 获取 '{title}' 内容失败: {e}")
        return None


if __name__ == "__main__":
    loader = MoegirlLoader("重音Teto")
    for doc in loader.lazy_load():
        print("—————————")
        if doc:
            print("标题:", doc.metadata["title"])
            print("正文:", doc.page_content)  # 打印前500个字符
        else:
            print("未找到内容。")
