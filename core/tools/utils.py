# core/tools/utils.py

"""
函数工具基类
"""

from langchain.agents import Tool
from typing import TYPE_CHECKING, final
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from ...bot import Bot


class BaseTool(ABC):
    """
    函数工具基类
    """

    bot: "Bot"
    name: str
    description: str

    def __init__(
        self,
        bot: "Bot",
        name: str,
        description: str = "",
    ):
        self.bot = bot
        self.name = name
        self.description = (
            description or self.__doc__ or f"No description provided for {self.__class__.__name__}"
        )

    @abstractmethod
    def run(self, query: str) -> str:
        """
        执行函数的主接口
        """

    @final
    @property
    def tool(self) -> Tool:
        return Tool(name=self.name, func=self.run, description=self.description)
