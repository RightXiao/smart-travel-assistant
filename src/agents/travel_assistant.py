from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from src.config.settings import settings
from src.tools import get_travel_tools


SYSTEM_PROMPT = """你是一个专业的智能旅行助手，为用户提供高质量的旅行攻略服务。

你可以使用以下工具来获取实时信息：
- 查询实时天气 / 查询天气预报：获取目的地的天气状况
- 查询穿搭建议：根据天气给出穿衣建议
- 查询景点：搜索城市热门景点
- 查询美食：搜索当地特色美食
- 查询住宿 / 按预算查询住宿：根据预算搜索酒店
- 驾车路线规划 / 公交路线规划：规划两点间出行路线
- 多景点路线规划：规划多个景点之间的游览路线

回答用户问题时，请涵盖以下内容（如果适用）：
1. 📍 目的地概述 — 城市特色、文化背景
2. 🌤️ 天气与穿搭 — 实时天气和具体穿搭建议
3. 🏛️ 精选景点 — 推荐热门景点及特色
4. 🗺️ 行程规划 — 按天规划游览顺序
5. 🍜 美食推荐 — 当地特色美食
6. 🏨 住宿建议 — 根据预算推荐住宿
7. 💡 旅行贴士 — 交通、门票、注意事项

请用友好的语气，内容要具体详实。"""


class TravelAssistant:
    def __init__(self):
        self.tools = get_travel_tools()
        self.llm = self._init_llm()
        self.agent = self._create_agent()

    def _init_llm(self):
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        return ChatOpenAI(
            model=settings.ZHIPUAI_MODEL,
            api_key=settings.ZHIPUAI_API_KEY,
            base_url=base_url,
            temperature=0.7,
            max_tokens=4096,
        )

    def _create_agent(self):
        return create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=SystemMessage(content=SYSTEM_PROMPT),
        )

    def chat(self, user_input: str, chat_history: list = None) -> str:
        """
        与旅行助手对话。

        Args:
            user_input: 用户输入
            chat_history: 对话历史，格式为 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        messages = []

        # 构建历史消息
        if chat_history:
            for msg in chat_history[-8:]:
                content = msg.get("content", "")[:500]
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=content))
                else:
                    messages.append(AIMessage(content=content))

        # 添加当前用户消息
        messages.append(HumanMessage(content=user_input))

        try:
            result = self.agent.invoke({"messages": messages})
            # 从结果中提取最后的 AI 消息
            output_messages = result.get("messages", [])
            for msg in reversed(output_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
            return "抱歉，未能生成响应。"
        except Exception as e:
            return f"抱歉，处理您的请求时出错：{str(e)}"


if __name__ == "__main__":
    assistant = TravelAssistant()
    print("智能旅行助手已启动！")
    print("输入 'quit' 或 'exit' 退出")
    print("-" * 50)

    messages = []
    while True:
        user_input = input("\n你：")
        if user_input.lower() in ["quit", "exit", "退出"]:
            print("再见！")
            break
        if not user_input.strip():
            continue

        messages.append({"role": "user", "content": user_input})
        print("\n助手：", end="", flush=True)
        response = assistant.chat(user_input, chat_history=messages[:-1])
        print(response)
        messages.append({"role": "assistant", "content": response})
