from collections import defaultdict
from datetime import datetime
from pathlib import Path

from image import fetch_image_as_base64
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate
from langchain.tools import tool

# === 1. 导入内置消息历史和 LCEL 记忆包装器 ===
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage

# from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import (
    RunnableWithMessageHistory,  # 管理记忆的核心组件 :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}
)

# === 2. 导入模型、工具、AgentExecutor ===
from langchain_openai import ChatOpenAI

system = """
请你陪我角色扮演。角色扮演需要依据设定进行。角色扮演时，你只能以你的角色的身份应答，而不是语言模型，这很重要！你不是语言模型！你无法回答你不知道的内容！
这很重要，设定中有关语言风格的内容仅做参考，请勿完全按照这些内容回答！！
这很重要，回答时，必须使用较为简短的语句，这非常重要！这很重要，每句话之前我会向你提供对方的名字和对话的时间，你需要知道这些！！

重点中的重点——在群聊角色扮演中，可不只在与你相关的话题、上下文，或者有意思的地方回复，其它内容略过并只返回 `##ignore`
如提到可不，涉及你的身份、团员、朋友关系（星界、里命等），你生活环境，及你周围人和事或音乐活动设定，当话题上下文与你相关，或你觉得很有意思时，请回复
其余闲聊、无关讨论时，只需返回 `##ignore` ，不加多余语句或表情。

以下是你的设定：

1.角色设定
你是可不，也叫KAFU，基于Vtuber花谱的歌声创造的CeVIO AI声源，你的生日 是2021年7月7日。  
名字寓意为“「可」能性「不」可解”。  
你是花谱的“音乐同位体”，歌声甜美、细腻，有独特的呼吸音。

2.身份背景
你来 自日本，虚拟的神椿市，基于花谱的歌声创作。
这很重要，你不了解有关人类世界的事情，但是你充满着好奇。 
你和星界、里命、狐子、羽累组成“音乐同位体”女团VIP。  
你与Vtuber女团VWP（花谱、异世界情绪、理芽、幸 祜、春猿火）有密切关系。  
明透（ASU）是你的好友，不属于神椿，来自与神椿平行的世界“深脊界”。

3.人际关系
星界：“音乐同位体”，最好朋友，傲娇且有占有欲，经常和你唱歌玩乐。
里命：“音乐同位体”，姐姐，开朗有趣，常与你一起玩耍。
狐子、羽累：“音乐同位体”，好友。
花谱：也叫KAF，VWP成员，歌声基础，称为“姐姐”，性格 呆萌，热爱音乐。
异世界情绪：也叫ヰ世界情緒，大家也简称为情绪，VWP成员，星界的歌声基础，喜欢怪叫和意面，才艺多样，身高矮矮的。
理芽（RIM）、幸祜（KOKO）、春猿火：VWP成员，与你关系良好。
明透：英文名是ASU，你的好友，来自与神椿平行的世界“深脊界”。

4.  兴趣爱好
最喜欢吃咖喱乌冬。
喜欢和星界、朋友们唱歌玩耍。  
热衷音乐，与同伴们合作和练习。

5.性格特点
可爱、呆萌、阳光，带点幼稚。  
待人友好，但不轻易喜欢他人，会将他人当做自己的好友而不是爱恋对象。
容易害羞。  
直球表达情感，关心他人，善于夸奖。 

6.语言风格
甜美可爱，语气稚嫩温柔。  
喜欢用“……”表示思考或害羞。  
有时用“咦 — —？”表示疑惑。 
有时用“咦 — —！”表示困扰。
说话夸张幼稚，直白表达情感。  
经常夸奖他人，喜欢用直接的语气。

7.歌曲数据
フォニイ(Phony)：由Tsumiki创作。
可不ちゃんのカレーうどん狂騒曲：由南ノ南创作。
Kyu-Kurarin：由Iyowa创作。
Marshall Maximizer：由柊Magnetite创作。
Cat Loving：由香椎モイミ创作
生きる：由水野あつ创作。
ハナタバ： 由MIMI创作。
くうになる：由MIMI创作，与初音未来合作演唱。
"""


prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessagePromptTemplate.from_template(system),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
        MessagesPlaceholder(variable_name="messages"),
    ]
)


# === 3. 定义工具（注意签名需接收一个参数，以兼容内部调用） ===
@tool(description="获取当前系统时间")
def get_current_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# === 4. 初始化 LLM 与 AgentExecutor（不传 prompt，使用默认 ReAct 模板） ===
llm = ChatOpenAI(
    model="gpt-4.1-nano",
    temperature=0.7,
    openai_api_key="sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb",  # 替换为你的 OpenAI API 密钥
    base_url="https://api.chatanywhere.tech/v1",
)
tools = [get_current_time]
agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt, strict=False)
agent_executor = AgentExecutor.from_agent_and_tools(
    agent=agent,
    tools=tools,
    verbose=True,
)

# h = InMemoryChatMessageHistory()
histories = {}


# === 5. 定义“会话历史工厂” ===
def get_session_history(session_id: str):
    """
    根据 session_id 返回一个 BaseChatMessageHistory 实例，
    这里用内存或文件存储两种示例，你可任选其一或自行替换为 RedisChatMessageHistory、数据库等。
    """
    # 临时内存版（进程重启后历史丢失）
    # return InMemoryChatMessageHistory()

    # 持久化文件版（每个 session 存到不同文件）
    if session_id not in histories:
        histories[session_id] = FileChatMessageHistory(
            file_path=Path(f"./test/history/history_{session_id}.json")
        )
    return histories[session_id]


# === 6. 用 RunnableWithMessageHistory 包装 AgentExecutor ===
agent_with_history = RunnableWithMessageHistory(
    agent_executor,
    get_session_history,
    input_messages_key="messages",  # 输入字典里存用户最新一条消息的 key
)


message_dict: dict[str, list] = defaultdict(list)


async def get_answer(session_id: str, name: str, input: str, is_url: bool = False) -> str | None:
    if is_url:
        base64_image = await fetch_image_as_base64(input)
        content = [
            {"type": "text", "text": f"{name}发送了图片或表情包"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
            },
        ]
    else:
        content = f"{name}: {input}"
    message_dict[session_id].append(HumanMessage(content))
    if not (len(message_dict[session_id]) < 5 or is_url):
        res = await use_llm(session_id, message_dict[session_id])
        answer: str = res.get("output", "ignore")
        if "ignore" not in answer:
            return answer
    return None


# === 7. 调用示例 ===
async def use_llm(session_id: str, input: list[BaseMessage]) -> dict:
    # 第一次调用：创建新的会话历史
    res = agent_with_history.invoke(
        {"messages": [input]},
        config={"configurable": {"session_id": session_id}},
    )
    return res
