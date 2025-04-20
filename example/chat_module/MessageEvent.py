# import json
import re

from chat_module.ChatAPI import ChatAPI

from sekaibot import Bot, Depends, Event
from sekaibot.adapter.cqhttp.event import MessageEvent
from sekaibot.adapter.cqhttp.message import CQHTTPMessageSegment

# from chat_module.CheckString import CheckString


# from sekaibot.exceptions import GetEventTimeout

'''
# 消息限制类
class MessageLimit:
    event: Event = Depends()
    bot: Bot = Depends()

    limit_list: dict[str, list[int]] = {"group": [788499440], "private": [], "blacklist": []}

    def is_message_allowed(self) -> bool:
        if self.event.user_id in self.limit_list["blacklist"]:
            return False
        """if self.info.message_type == 'group':
            group_allowed = self.info.group_id not in self.limit_list['group'] or self._count_message(self.info.group_id)
            private_allowed = self.info.user_id not in self.limit_list['private'] or self._count_message(self.info.user_id)
            return group_allowed and private_allowed"""
        if self.event.message_type == "private":
            return self._count_message(self.event.user_id)
        return True

    def _count_message(self, id_: int) -> bool:
        if self.bot.global_state.get("message_limit") is None:
            self.bot.global_state["message_limit"] = defaultdict(list)

        current_time = time.time()
        message_times: list[float] = self.bot.global_state["message_limit"][id_]
        message_times = [
            timestamp for timestamp in message_times if current_time - timestamp <= 600
        ]
        self.bot.global_state["message_limit"][id_] = message_times
        if len(message_times) >= 4:
            return False
        self.bot.global_state["message_limit"][id_].append(current_time)
        return True
'''


class GetApi:
    bot: Bot = Depends()

    def __enter__(self) -> ChatAPI:
        # if self.bot.global_state.get('chat_system') is None:
        # with BaseConfig(self.bot) as config:
        # self.bot.global_state['chat_system'] = ChatAPI(CharacterConfig=config._character_config,MySQLConfig=config._mysql_config,RedisConfig=config._redis_config)
        return self.bot.global_state["chat_system"]

    def __exit__(self, exc_type, exc_value, traceback):
        return False


# 具体消息返回类
class ChatHandler:
    bot: Bot = Depends()
    event: MessageEvent = Depends(Event)
    chat_api: ChatAPI = Depends(GetApi)

    @staticmethod
    def extract_music_titles(text):
        # 使用正则表达式提取书名号《》括起来的内容
        pattern = r"《(.*?)》"
        return re.findall(pattern, text)

    async def respond_to_message(self, if_img: bool = True, if_music: bool = True) -> None:
        meme = False
        answer = None
        if len(self.event.get_plain_text()) > 150:
            answer = "请勿发送过长内容！！"
        else:
            if len(self.event.message) == 1 and self.event.message[0].type == "image":
                for msg in self.event.message:
                    img_url = msg.data.get("url")
                    meme = True
                    answer = await self.chat_api.get_img_ai_answer(
                        user_id=self.event.user_id, img_url=img_url, timeout=15
                    )
            elif self.event.reply:
                answer = await self.chat_api.get_ai_answer(
                    user_id=self.event.user_id,
                    text=self.event.get_plain_text(),
                    name=self.event.sender.nickname,
                    reply=self.event.reply,
                    use_tool=True if self.event.message_type == "group" else False,
                    timeout=10,
                )
            else:
                answer = await self.chat_api.get_ai_answer(
                    user_id=self.event.user_id,
                    text=self.event.get_plain_text(),
                    name=self.event.sender.nickname,
                    use_tool=True if self.event.message_type == "group" else False,
                    timeout=10,
                )
        if answer is None or answer == "":
            await self.chat_api.chat_system.clear_memory(self.event.user_id)
        if isinstance(answer, str):
            """if not meme:
                response = CQHTTPMessageSegment.reply(self.event.message_id)
                response += (
                    CQHTTPMessageSegment.at(self.event.user_id)
                    + CQHTTPMessageSegment.text(" " + answer)
                    if self.event.message_type == "group"
                    else CQHTTPMessageSegment.text(answer)
                )
            else:
                response = (
                    CQHTTPMessageSegment.at(self.event.user_id)
                    + CQHTTPMessageSegment.text(" " + answer)
                    if self.event.message_type == "group"
                    else CQHTTPMessageSegment.text(answer)
                )"""
            # self.answer = answer
            if meme:
                await self.event.adapter.send(self.event, answer, at_sender=True)
            else:
                await self.event.adapter.send(
                    self.event, answer, at_sender=True, reply_message=True
                )
            """if if_music:
                substring = self.extract_music_titles(answer)
                if substring != []:
                    music_dict = get_music_dict()
                    substring = substring[0]
                    best_match = process.extractOne(substring, list(music_dict.keys()))
                    music = best_match[0]
                    point = best_match[1]
                    if point >= 70:
                        music_id = music_dict[music]
                        music_msg = CQHTTPMessageSegment.music(type_="163", id_=music_id)
                        await self.event.adapter.send(self.event, music_msg)"""
        else:
            if answer.tool_calls is not None:
                tool = answer.tool_calls[0]
                await getattr(self, f"_{tool.function.name}_tool")(tool)

    """
    async def _get_person_from_name(self, name):
        group_member = await self.event.adapter.get_group_member_list(group_id=self.event.group_id)
        return await CheckString().check_user_in_str(name, group_member)

    async def _poke_message_tool(self, tool: ChatCompletionMessageToolCall):
        target = await self._get_person_from_name(
            json.loads(tool.function.arguments)["target_name"]
        )
        if target is not None:
            await self.event.adapter.group_poke(
                group_id=self.event.group_id, user_id=target["user_id"]
            )
    """

    """
    async def _send_message_to_others_tool(self, tool: ChatCompletionMessageToolCall):
        arguments = json.loads(tool.function.arguments)
        target_n = arguments.get("target_name", None).strip()
        target = await self._get_person_from_name(target_n)
        if target is not None:
            message = CQHTTPMessageSegment.at(target["user_id"]) + CQHTTPMessageSegment.text(
                " " + arguments["message"]
            )
            await self.event.adapter.send(
                self.event, message_=message, message_type="group", id_=self.event.group_id
            )
            print(target["user_id"])
            if (
                target["is_robot"]
                or target["user_id"] in [3976491019, 3988189771, 2475268559]
                or target_n in ["可不", "星界", "里命"]
            ):
                try:
                    await self.event.adapter.get(
                        lambda info, event: (
                            info.type == "message" and info.sender.user_id == target["user_id"]
                        ),
                        timeout=30,
                    )
                except GetEventTimeout:
                    pass
        elif target_n != "":
            message = CQHTTPMessageSegment.text(f"@{target_n}") + CQHTTPMessageSegment.text(
                " " + arguments["message"]
            )
            await self.event.adapter.send(
                self.event, message_=message, message_type="group", id_=self.event.group_id
            )
    """

    async def _clear_chat_memory_tool(self, tool) -> None:
        response1 = CQHTTPMessageSegment.reply(self.event.message_id) + CQHTTPMessageSegment.text(
            "------------记忆已清除------------"
        )
        await self.event.adapter.send(self.event, response1)
        answer = await self.chat_api.clear_ai_memory(
            user_id=self.event.user_id, name=self.event.sender.nickname
        )
        response2 = (
            CQHTTPMessageSegment.at(self.event.user_id) + CQHTTPMessageSegment.text(" " + answer)
            if self.event.message_type == "group"
            else CQHTTPMessageSegment.text(answer)
        )
        await self.event.adapter.send(self.event, response2)

    '''
    async def respond_to_poke(self, if_img: bool = True) -> None:
        answer = await self.chat_api.get_ai_answer(
            user_id=self.event.user_id, text=self.event.poke_text, name=self.event.user_name
        )
        response = (
            CQHTTPMessageSegment.at(self.event.user_id) + CQHTTPMessageSegment.text(" " + answer)
            if self.event.message_type == "group"
            else CQHTTPMessageSegment.text(answer)
        )
        await self.call_back(response)

        # Uneventent if you want to handle emojis or images for poke responses
        """
        if if_img:
            emoji, music = await self.chatMemoryBD.analyze_response(answer)
            if emoji:
                img = self.get_meme_message(self.emoji_list[emoji]["imageId"], self.emoji_list[emoji]["url"])
                await self.event.adapter.send(self.event, img)
        """
    '''
