# 免费：sk-ADX97OSA3STCkdmZRruOwzScdpPueRZ6ucOD2orI0ZszZ7Xn  sk-5I6iX4e1MiCiyAmjHZFF13EVFFGeZMog08HT9ejFqjz2iWwr
# 付费：sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb
# Deepseek: sk-4d5b136754f24f639ba44d63441826b2
import asyncio

import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

key = "sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb"  #'sk-bhdmqdxarfvvcnkxzfhsmffedaplcfngwxhyrjymfgzxmqqs'
base_url = "https://api.chatanywhere.tech/v1"  #'https://api.siliconflow.cn/v1'
model = "gpt-4o-mini"  #'deepseek-ai/DeepSeek-V3'


class ChatGPT:
    client: AsyncOpenAI

    def __init__(self):
        self.log = structlog.stdlib.get_logger().bind(name="chat_gpt")
        self.client = AsyncOpenAI(api_key=key, base_url=base_url)

    async def gpt_4_mini_api(
        self, messages: list, use_tool: bool = False, temperature=1, timeout=60
    ) -> str | ChatCompletionMessage:
        """调用 GPT-4 Mini API"""
        self.log.info("Successfully using chatgpt api key", key=key)
        tools = [
            '''{
                "type": "function",
                "function": {
                    "name": "poke_message",
                    "description": "这很重要，有关键词优先考虑本函数，对某人发出“戳戳”、“拍拍”、“亲亲”、“抱抱”、“揉揉”等类似消息。如果没有明确指定是谁，就默认是对方",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_name": {
                                "type": "string",
                                "description": "目标对象的名字，严格根据对话得出，可能是你不认识的人。如果对话没体现，默认是对方",
                            },
                        },
                        "required": ["target_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_message_to_others",
                    "description": "如果聊天中让你对另一人发出消息，比如让你直接说，或者转达等，调用本函数",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_name": {
                                "type": "string",
                                "description": "目标对象的名字，严格根据对话得出，可能是你不认识的人",
                            },
                            "message": {
                                "type": "string",
                                "description": "对目标对象发送的消息，转达时注意人称",
                            },
                        },
                        "required": ["target_name", "message"],
                    },
                },
            },'''
        ]
        clear_tools = [
            {
                "type": "function",
                "function": {
                    "name": "clear_chat_memory",
                    "description": "用户发出清除当前对话的记忆、历史、上下文要求，或者说忘记历史，记忆等类似要求时，调用本函数，这很重要",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]
        completion = (
            (
                await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=timeout,
                    tools=clear_tools,
                    temperature=temperature,
                )
            )
            if use_tool
            else (
                await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    timeout=timeout,
                    tools=clear_tools,
                    temperature=temperature,
                )
            )
        )
        content = completion.choices[0].message.content
        return content if content is not None else completion.choices[0].message

    async def get_answer(
        self, messages: dict, use_tool: bool = False, temperature=0.7, timeout=6, key: str = None
    ):
        try:
            answer_text = await self.gpt_4_mini_api(messages, use_tool, temperature, timeout)
        except TimeoutError:
            self.log.error("TimeoutError: Get answers timeout")
            return asyncio.TimeoutError
        else:
            self.log.info(f"Successfully get chatgpt answer:\n{answer_text}")
            return answer_text
