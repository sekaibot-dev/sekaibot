# utils.py
import re

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
