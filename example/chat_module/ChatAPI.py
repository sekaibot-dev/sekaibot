import json
import time
from typing import Literal

from chat_module.ChatGPT import ChatCompletionMessage, ChatGPT
from chat_module.ChatMemory import ChatMemoryDB
from chat_module.config import CharacterConfig
from chat_module.image import fetch_image_as_base64

from sekaibot.adapter.cqhttp.event import Reply

# from sekaibot.info import ReplyMessage


# AI接口类
class ChatAPI:
    def __init__(self, character_config: CharacterConfig, mysql_config: dict, redis_config: dict):
        self._chat_api = ChatGPT()
        self.config = character_config
        self.chat_system = ChatMemoryDB(db_config=mysql_config, redis_config=redis_config)

    @staticmethod
    def _format_time() -> str:
        """格式化当前时间"""
        return time.strftime("%m月%d日%H点%M分", time.localtime())

    def _generate_system_test(self) -> list[dict]:
        """生成系统消息集合"""
        return [
            self._add_message(
                f"{self.config.talk_set['prompt']}\n{self.config.talk_set['content']}",
                role="system",
            ),
            self._add_message(
                f"{self.config.info_set['prompt']}\n{self.config.info_set['content']}",
                role="system",
            ),
        ]

    def _add_message(self, text: str, role: Literal["user", "assistant", "system"]) -> dict:
        """添加消息到会话中"""
        return {"role": role, "content": text}

    async def _format_message(
        self,
        text: str,
        name: str = None,
        reply: Reply = None,
        _type: Literal["user", "assistant"] = "user",
    ):
        conversation = []
        if _type == "user":
            nowtime = self._format_time()
            if reply is not None and reply.message.get_plain_text().strip() != "":
                conversation.append(
                    self._add_message(
                        text=[
                            {
                                "type": "text",
                                "text": f"引用消息：\n时间：{nowtime}; 用户“{reply.sender.nickname}”: \n{reply.message.get_plain_text()}",
                            },
                            {
                                "type": "text",
                                "text": f"时间：{nowtime}; 用户“{name}”: \n{text}",
                            },
                        ],
                        role="user",
                    )
                )
            elif (
                reply is not None
                and len(reply.message) == 1
                and reply.message[0].type == "image"
                and reply.message_type == "group"
            ):
                img_url = reply.message[0].data.get("url")
                base64_image = await fetch_image_as_base64(img_url)
                conversation.append(
                    self._add_message(
                        text=[
                            {
                                "type": "text",
                                "text": "分享了一张表情包，你要优先根据你的外貌判断是不是你或者根据印象判断是不是你认识的人。如果认出来了就笃定地根据判断结果回答；无法认出就不用体现在对话中，转向注重表情的含义和情感。请简短回答。",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                            {
                                "type": "text",
                                "text": f"时间：{nowtime}; 用户“{name}”: \n{text}",
                            },
                        ],
                        role="user",
                    )
                )
            else:
                conversation.append(
                    self._add_message(text=f"时间：{nowtime}; 用户“{name}”: \n{text}", role="user")
                )
        else:
            conversation.append(self._add_message(text=text, role="assistant"))
        return conversation

    async def get_ai_answer(
        self,
        user_id: int,
        text: str,
        name: str,
        reply: Reply = None,
        use_tool: bool = False,
        timeout=None,
    ) -> str | ChatCompletionMessage:
        character_config = self._generate_system_test()
        memory = await self.chat_system.get_memory(user_id)
        key = None
        if "image" in str(memory):
            key = "sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb"
        conversation = await self._format_message(text=text, name=name, reply=reply)
        messages = character_config + memory + conversation
        try:
            response = await self._chat_api.get_answer(
                messages=messages, key=key, use_tool=use_tool, timeout=timeout
            )
        except TimeoutError:
            response = "可不记不起来你说什么了，请再试一次哦"
            return response
        else:
            if isinstance(response, str):
                conversation += await self._format_message(text=response, _type="assistant")
                await self.chat_system.add_memory(user_id=user_id, message=conversation)
                return response
            else:
                conversation += [
                    {
                        "role": "assistant",
                        "tool_calls": response.model_dump()["tool_calls"],
                    },
                    {
                        "role": "tool",
                        "content": json.dumps(
                            json.loads(response.tool_calls[0].function.arguments)
                            | {response.tool_calls[0].function.name + "response": "Done"}
                        ),
                        "tool_call_id": response.tool_calls[0].id,
                    },
                ]
                await self.chat_system.add_memory(user_id=user_id, message=conversation)
                return response

    async def get_img_ai_answer(self, user_id: int, img_url: str, timeout=None) -> str:
        character_config = self._generate_system_test()
        memory = await self.chat_system.get_memory(user_id)
        base64_image = await fetch_image_as_base64(img_url)
        conversation = [
            self._add_message(
                text=[
                    {
                        "type": "text",
                        "text": "分享了一张表情包，你要优先根据你的外貌判断是不是你或者根据印象判断是不是你认识的人。如果认出来了就笃定地根据判断结果回答；无法认出就不用体现在对话中，转向注重表情的含义和情感。请简短回答。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
                role="user",
            )
        ]
        messages = character_config + memory + conversation
        try:
            response = await self._chat_api.get_answer(
                messages=messages,
                key="sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb",
                timeout=timeout,
            )
        except TimeoutError:
            response = "可不记不起来你说什么了，请再试一次哦"
        else:
            conversation += await self._format_message(text=response, _type="assistant")
            await self.chat_system.add_memory(user_id=user_id, message=conversation)
        return response

    async def clear_ai_memory(self, user_id, name, text: str = "你好") -> str:
        await self.chat_system.clear_memory(user_id)
        return await self.get_ai_answer(user_id=user_id, text=text, name=name)
    
    async def close(self):
        await self.chat_system.close()
