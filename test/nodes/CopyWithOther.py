from typing import Any

from sekaibot import Node
from sekaibot.adapters.cqhttp.event import GroupMessageEvent
from sekaibot.adapters.cqhttp.message import CQHTTPMessage, CQHTTPMessageSegment


class CopyWith(Node[GroupMessageEvent, dict, Any]):
    priority: int = 2

    async def handle(self) -> None:
        def del_file_id(msg: CQHTTPMessageSegment):
            msg.data.pop("file_id", None)
            msg.data.pop("url", None)
            msg.data.pop("file", None)
            return msg

        message = repr(CQHTTPMessage(list(map(del_file_id, self.event.message))))
        if self.event.group_id in self.node_state:
            if message in self.node_state[self.event.group_id]:
                self.node_state[self.event.group_id][message] += 1
                if self.node_state[self.event.group_id][message] >= 3:
                    self.node_state[self.event.group_id] = {}
                    await self.call_api(
                        "forward_group_single_msg",
                        message_id=self.event.message_id,
                        group_id=self.event.group_id,
                    )
                    self.stop()
            else:
                self.node_state[self.event.group_id] = {message: 1}
        else:
            self.node_state[self.event.group_id] = {message: 1}

    async def rule(self) -> bool:
        return (not self.event.is_tome()) and self.event.user_id != 2854196310
