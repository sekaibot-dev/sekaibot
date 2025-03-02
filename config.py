# config.py
import os
from typing import List, Dict, Literal
from pydantic import BaseModel

class Config():
    # 你的 OpenAI API Key
    api_key: str = "sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb"#os.getenv("OPENAI_API_KEY", "your-openai-api-key")
    base_url: str = "https://api.chatanywhere.tech/v1"

    # 使用的 OpenAI 模型（这里示例 GPT-4，可根据需求调整）
    model: str = "gpt-4o-mini"

    # Redis 连接配置
    # 如果你本地使用默认6379端口，可以写成 "redis://localhost:6379"
    redis_url: str = "redis://localhost:6379"#os.getenv("REDIS_URL", "redis://localhost:6379")

    name: str = "星界"
    # 群聊关键词列表（示例）
    keywords: Dict[Literal["main","normal",""],List[str]] = {
        "Tier_1": {
            "description": "核心关键词：直接与主题强相关，具有最高优先级",
            "keywords": [
                "核心关键词1",
                "核心关键词2",
                "核心关键词3",
            ]
        },
        "Tier_2": {
            "description": "重要关键词：对主题的补充，帮助细化方向",
            "keywords": [
                "重要关键词1",
                "重要关键词2",
                "重要关键词3",
            ]
        },
        "Tier_3": {
            "description": "次要关键词：关联较低但增加表达的多样性",
            "keywords": [
                "次要关键词1",
                "次要关键词2",
                "次要关键词3",
            ]
        },
        "Tier_4": {
            "description": "边缘关键词：偶尔出现，用于拓展可能性",
            "keywords": [
                "边缘关键词1",
                "边缘关键词2",
                "边缘关键词3",
            ]
        }
    }

    # 角色信息，示例给出一个简单的背景设定
    role_definition: str = (
        "你是一个善解人意、幽默风趣的AI助理，会根据用户的上下文对话内容进行自然回答。你叫James。"
        "请注意对话场景的合理性，并结合用户和系统信息。"
    )
    symbol_conversation: List[Dict[str, str | List[str | Dict]]] = [
        {"input": "我喜欢你", "output": "（眼睛微微睁大，脸颊轻微染上红晕，轻轻转身，不敢直视）……你真是，真是的，突然说这种话……不、不知道该怎么回答呢……"}
    ]
    mood_settings: Dict[int, str] = {
        
    }
