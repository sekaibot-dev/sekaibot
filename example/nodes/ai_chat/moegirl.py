import re
from collections.abc import Iterator

import mwparserfromhell
import requests
from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document


def beautify_text(raw: str) -> str:
    """把 strip_code 输出的纯文本进一步整理为 Markdown 风格"""
    lines: list[str] = []
    for line in raw.splitlines():
        line = line.rstrip()  # 去掉行尾空白
        if not line:
            lines.append("")  # 保留空行，后续再折叠
            continue

        # ---------- 标题 ----------
        # ====== Title ======   →  ## Title
        m = re.fullmatch(r"(=+)\s*(.+?)\s*=*", line)
        if m:
            level = min(len(m.group(1)), 6)  # 最多 6 级
            lines.append("#" * level + " " + m.group(2).strip())
            continue

        # ---------- 列表 ----------
        # ① xxx / 1. xxx / - xxx / ・xxx
        if re.match(r"^\s*[\u2460-\u24fe\u2474-\u249c0-9]+[\.、．）)]\s+\S", line):
            # 编号列表 → 1. xxx
            line = re.sub(
                r"^\s*([\u2460-\u24fe\u2474-\u249c0-9]+)[\.、．）)]\s+",
                "1. ",
                line,
            )
        elif re.match(r"^\s*[・·*\-•‣]\s+\S", line):
            line = re.sub(r"^\s*[・·*\-•‣]\s+", "- ", line)
        lines.append(line.strip())

    # ---------- 空行折叠 ----------
    beautified = []
    blank = False
    for ln in lines:
        if ln:
            beautified.append(ln)
            blank = False
        else:
            if not blank:  # 保留 1 个空行
                beautified.append("")
            blank = True

    return "\n".join(beautified).strip()


class MoegirlLoader(BaseLoader):
    """萌娘百科文档加载器，支持折叠内容"""

    def __init__(
        self,
        query: str,
        lang: str = "zh",
        doc_content_chars_max: int = 40000,
    ):
        self.query = query
        self.doc_content_chars_max = doc_content_chars_max
        self.api_url = f"https://{lang}.moegirl.org.cn/api.php"

    # ---------- public --------------------------------------------------
    def lazy_load(self) -> Iterator[Document]:
        content = self._fetch_content(self.query)
        if content:
            if self.doc_content_chars_max:
                content = content[: self.doc_content_chars_max]
                content = beautify_text(content)
            yield Document(
                page_content=content,
                metadata={"source": "moegirl", "title": self.query},
            )

    # ---------- private -------------------------------------------------
    def _fetch_content(self, title: str) -> str | None:
        """改用 action=query&prop=revisions 拿 wikitext，再转纯文本"""
        params = {
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvslots": "main",  # MediaWiki 1.35+
            "rvprop": "content",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,  # 自动跟随重定向
        }

        try:
            r = requests.get(
                self.api_url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            if not pages or "revisions" not in pages[0]:
                return None

            wikitext = pages[0]["revisions"][0]["slots"]["main"]["content"]
            # ---- wikitext → plain text --------------------------------
            wikicode = mwparserfromhell.parse(wikitext)
            return wikicode.strip_code(normalize=True, collapse=True).strip()
        except Exception as e:
            print(f"[错误] 获取 '{title}' 内容失败: {e}")
            return None


if __name__ == "__main__":
    loader = MoegirlLoader("花谱")
    for doc in loader.lazy_load():
        print("—————————")
        if doc:
            print("标题:", doc.metadata["title"])
            print("正文:", doc.page_content)
        else:
            print("未找到内容。")
