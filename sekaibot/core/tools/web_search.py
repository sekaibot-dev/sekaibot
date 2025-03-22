# core/tools/web_search.py
from langchain.agents import Tool


class WebSearchTool:
    """
    示例性的 Web 搜索工具。
    实际可使用 google、serpapi 或其他搜索库进行实现。
    这里只是一个占位示例。
    """

    def __init__(self):
        pass

    def _run_search(self, query: str) -> str:
        # 这里写搜索的逻辑，比如调用 Google Serper API
        # 或者只做一个 mock：
        return f""

    def run(self, query: str) -> str:
        return self._run_search(query)

    def to_tool(self) -> Tool:
        return Tool(
            name="web_search",
            func=self.run,
            description="可以帮助进行网络搜索，输入搜索关键词，返回搜索结果",
        )
