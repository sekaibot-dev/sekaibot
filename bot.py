import asyncio
from typing import (
    Optional,
    Dict,
    Tuple,
    List,
    Set,
    Any,
    Type,
    Callable,
    Awaitable,
    Union,
)
import json
from config import ConfigModel, MainConfig
from log import Logger
from core.agent_executor import ChatAgentExecutor
import sys
from pathlib import Path
from pydantic import (
    ValidationError,
    create_model,  # pyright: ignore[reportUnknownVariableType]
)
from .utils import (
    ModulePathFinder,
    get_classes_from_module_name,
    is_config_class,
    samefile,
    wrap_get_func,
    validate_instance
)

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

def check_group_keywords(text: str, keywords: list) -> bool:
    """
    检查文本中是否包含任意关键字，返回 True 或 False
    """
    for kw in keywords:
        if kw in text:
            return True
    return False

def is_at_bot(event: dict) -> bool:
    """
    根据 event 判断是否 at 了 bot。
    规则：如果 event['startwith_atbot'] == True，则认为 at 了 bot
    """
    return event.get("startwith_atbot", False)

def is_private_message(event: dict) -> bool:
    """
    判断是否是私聊消息
    """
    return event.get("message_type") == "private"

class Bot():
    config: MainConfig
    logger: Logger

    _config_file: str | None  # 配置文件
    _config_dict: Dict[str, Any] | None  # 配置

    def __init__(
        self,
        *,
        config_file: str | None = "config.toml",
        config_dict: Dict[str, Any] | None = None,
    ):
        """初始化 SekaiBot，读取配置文件，创建配置。

        Args:
            config_file: 配置文件，如不指定则使用默认的 `config.toml`。
                若指定为 `None`，则不加载配置文件。
            config_dict: 配置字典，默认为 `None。`
                若指定字典，则会忽略 `config_file` 配置，不再读取配置文件。
        """
        self.config = MainConfig()
        self.logger = Logger(self)

        self._config_file = config_file
        self._config_dict = config_dict

        self.chat_agent = ChatAgentExecutor(
            bot=self,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model_name=self.config.model,
            redis_url=self.config.redis_url
        )
        
    def _update_config(self) -> None:
        """更新 config，合并入来自 Plugin 和 Adapter 的 Config。"""

        '''def update_config(
            source: List[Type[Plugin[Any, Any, Any]]] | List[Adapter[Any, Any]],
            name: str,
            base: Type[ConfigModel],
        ) -> Tuple[Type[ConfigModel], ConfigModel]:
            config_update_dict: Dict[str, Any] = {}
            for i in source:
                config_class = getattr(i, "Config", None)
                if is_config_class(config_class):
                    default_value: Any
                    try:
                        default_value = config_class()
                    except ValidationError:
                        default_value = ...
                    config_update_dict[config_class.__config_name__] = (
                        config_class,
                        default_value,
                    )
            config_model = create_model(name, **config_update_dict, __base__=base)
            return config_model, config_model()

        self.config = create_model(
            "Config",
            plugin=update_config(self.plugins, "PluginConfig", PluginConfig),
            adapter=update_config(self.adapters, "AdapterConfig", AdapterConfig),
            __base__=MainConfig,
        )(**self._raw_config_dict)'''

        self.logger._load_logger()

    def _reload_config_dict(self) -> None:
        """重新加载配置文件。"""
        self._raw_config_dict = {}

        if self._config_dict is not None:
            self._raw_config_dict = self._config_dict
        elif self._config_file is not None:
            try:
                with Path(self._config_file).open("rb") as f:
                    if self._config_file.endswith(".json"):
                        self._raw_config_dict = json.load(f)
                    elif self._config_file.endswith(".toml"):
                        self._raw_config_dict = tomllib.load(f)
                    else:
                        self.logger.error(
                            "Read config file failed: "
                            "Unable to determine config file type"
                        )
            except OSError:
                self.logger.exception("Can not open config file:")
            except (ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError):
                self.logger.exception("Read config file failed:")

        try:
            self.config = MainConfig(**self._raw_config_dict)
        except ValidationError:
            self.config = MainConfig()
            self.logger.exception("Config dict parse error")
        self._update_config()

    
    def get_session_id(self, event: dict):
        if is_private_message(event):
            return "user_" + str(event.get("user_id"))
        else:
            return "group_" + str(event.get("group_id"))

    def check_answer(self, event: dict) -> bool:
        
        if is_private_message(event):
            return True
        is_group = (event.get("message_type") == "group")
        group_keywords_hit = False
        if is_group:
            group_keywords_hit = check_group_keywords(event.get("plain_text", ""), self.config.keywords)
        return is_at_bot(event) or (is_group and group_keywords_hit)
        
        

    async def handle_message(self, event: dict) -> Optional[str]:
        """
        核心消息处理入口：
        1. 判断是否需要回复：
        - 私聊 or (群聊且 at_bot==True) or (群聊且命中关键词)
        2. 如果需要回复，调用 LangChain Agent 获取回复并返回。
        3. 如果不需要回复，仅做消息存储，返回 None。
        """
        session_id = self.get_session_id(event)
        
        if not self.check_answer(event):
            await self.chat_agent.memory_manager.add_message(
                session_id=session_id,
                role="user",
                input=event.get("plain_text"),
                timestamp=int(event.get("time")),
                message_id=str(event.get("message_id"))
            )
            return None
        
        reply = (await self.chat_agent.run(
            message=event, 
            session_id=session_id,
            timestamp=int(event.get("time")),
            message_id=str(event.get("message_id")), 
        ))

        return reply

    

if __name__ == "__main__":
    # 示例：模拟私聊测试
    sample_event_private = {
        "type": "message",
        "time": 1738559871,
        "self_id": 3988189771,
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": 24495503,
        "user_id": 2122331,
        "plain_text": "我是谁",
        "user_name": "Miku",
        "ask_bot": True,
        "startwith_atbot": False
    }

    # 示例：模拟群聊测试
    sample_event_group = {
        "type": "message",
        "time": 1738559959,
        "self_id": 3988189771,
        "post_type": "message",
        "message_type": "group",
        "group_id": 89411261,
        "message_id": 1593257552,
        "user_id": 26820646331,
        "plain_text": "我叫什么名字",
        "user_name": "Miku",
        "ask_bot": False,
        "startwith_atbot": True
    }
    bot = Bot(Config())

    async def run_test():
        resp1 = await bot.handle_message(sample_event_private)
        print("私聊回复:", resp1)

        resp2 = await bot.handle_message(sample_event_group)
        print("群聊回复:", resp2)

    asyncio.run(run_test())
