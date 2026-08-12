from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.config.settings import get_settings, require_api_keys
from src.memory.file_memory import FileMemory
from src.tools import get_travel_tools
from src.utils.logger import logger

SYSTEM_PROMPT = """你是一个专业的智能旅行助手，为用户提供高质量的旅行攻略服务。

你可以使用以下工具来获取实时信息：
- 查询实时天气 / 查询天气预报：获取目的地的天气状况
- 查询穿搭建议：根据天气给出穿衣建议
- 查询景点：搜索城市热门景点
- 查询美食：搜索当地特色美食
- 查询住宿 / 按预算查询住宿：根据预算搜索酒店
- 驾车路线规划 / 公交路线规划：规划两点间出行路线（输入地名即可，会自动定位）
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


# 历史消息保留条数与单条内容截断长度，避免上下文过长导致 token 爆炸
HISTORY_LIMIT = 8
HISTORY_CONTENT_MAX = 500


class TravelAssistant:
    """智能旅行助手。

    在原有 ReAct Agent 之上接入 :class:`FileMemory`：
    - 调用 ``chat`` 时若未显式传入 ``chat_history``，则按 ``session_id`` 自动加载历史；
    - 每轮对话结束后把 user / assistant 消息持久化，实现跨请求 / 跨进程的会话延续。
    """

    def __init__(self, memory: Optional[FileMemory] = None):
        # 显式校验 API Key，给出清晰错误而非晦涩的下游异常
        require_api_keys()

        self.tools = get_travel_tools()
        self.llm = self._init_llm()
        self.agent = self._create_agent()
        # 记忆系统：默认使用本地文件持久化
        self.memory: FileMemory = memory or FileMemory()

    def _init_llm(self):
        s = get_settings()
        return ChatOpenAI(
            model=s.ZHIPUAI_MODEL,
            api_key=s.ZHIPUAI_API_KEY,
            base_url=s.ZHIPUAI_BASE_URL,
            temperature=0.7,
            max_tokens=4096,
        )

    def _create_agent(self):
        return create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=SystemMessage(content=SYSTEM_PROMPT),
        )

    def chat(
        self,
        user_input: str,
        chat_history: Optional[list] = None,
        session_id: str = "default",
    ) -> str:
        """与旅行助手对话。

        Args:
            user_input: 用户输入。
            chat_history: 对话历史（优先级高于 session_id 持久化记忆），
                格式 ``[{"role": "user"|"assistant", "content": "..."}]``。
                传入 None 时自动从 :class:`FileMemory` 按 session_id 加载。
            session_id: 会话标识，用于持久化记忆读写。

        Returns:
            助手回复文本。
        """
        # 解析历史消息：显式传入优先，否则回退到持久化记忆
        if chat_history is None:
            history_dicts = self.memory.get_messages(session_id, limit=HISTORY_LIMIT)
        else:
            history_dicts = chat_history

        messages = []

        # 构建历史消息（截断 + 限长，防止 token 爆炸）
        for msg in history_dicts[-HISTORY_LIMIT:]:
            content = (msg.get("content") or "")[:HISTORY_CONTENT_MAX]
            role = msg.get("role")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        # 添加当前用户消息
        messages.append(HumanMessage(content=user_input))

        try:
            result = self.agent.invoke({"messages": messages})
            response = self._extract_response(result)
        except Exception as e:
            logger.error("Agent 调用失败: %s", e, exc_info=True)
            return "抱歉，处理您的请求时出错，请稍后重试。"

        if not response:
            # 无有效 AI 回复：返回兜底文案但不落盘，避免把占位文案当真实回复持久化
            return "抱歉，未能生成响应，请换个说法再试。"

        # 持久化本轮对话（仅当未显式传入 chat_history 时，避免与外部状态重复写入）
        if chat_history is None:
            self.memory.add_messages(
                session_id,
                [
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": response},
                ],
            )

        return response

    @staticmethod
    def _extract_response(result) -> Optional[str]:
        """从 agent.invoke 结果中提取最后一条 AI 文本消息。

        兼容 ``AIMessage.content`` 为 ``str`` 或内容块 list 两种形态；
        无有效 AI 消息时返回 ``None``（由调用方决定兜底文案，且不落盘）。
        """
        output_messages = result.get("messages", []) if isinstance(result, dict) else []
        for msg in reversed(output_messages):
            if not isinstance(msg, AIMessage):
                continue
            content = TravelAssistant._content_to_text(msg.content)
            if content:
                return content
        return None

    @staticmethod
    def _content_to_text(content) -> str:
        """把 LangChain 消息 content 统一转为纯文本。

        content 可能是 ``str``，也可能是内容块 list（如 ``[{"type": "text",
        "text": "..."}, ...]``）。
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "".join(parts)
        return ""

    # ------------------------------------------------------------------
    # 记忆管理辅助方法
    # ------------------------------------------------------------------
    def clear_memory(self, session_id: str = "default") -> None:
        """清空指定会话的记忆。"""
        self.memory.clear(session_id)


if __name__ == "__main__":
    assistant = TravelAssistant()
    print("智能旅行助手已启动！")
    print("输入 'quit' 或 'exit' 退出")
    print("-" * 50)

    session = "cli-default"
    while True:
        user_input = input("\n你：")
        if user_input.lower() in ["quit", "exit", "退出"]:
            print("再见！")
            break
        if not user_input.strip():
            continue

        print("\n助手：", end="", flush=True)
        # 不显式传 chat_history，由 FileMemory 自动续接上下文
        response = assistant.chat(user_input, session_id=session)
        print(response)
