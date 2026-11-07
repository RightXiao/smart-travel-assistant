"""智能旅行助手 Agent（ReAct + 持久化记忆 + 用户画像 + 流式事件 + 行程规划）。

在 LangGraph ``create_react_agent`` 之上提供：

- **会话记忆**：``MEMORY_BACKEND=file|sqlite`` 选择后端；未显式传
  ``chat_history`` 时按 ``session_id`` 自动加载历史并在每轮后落盘；
- **历史窗口**：近 ``AGENT_HISTORY_LIMIT`` 条直传，更早消息压缩为摘要；
- **用户画像**：从用户输入抽取偏好（目的地/天数/预算/兴趣标签），
  持久化后以 SystemMessage 注入实现个性化；
- **可观测性**：每轮记录耗时与 token 用量（:class:`TokenUsageHandler`）；
- **流式事件**：``astream_chat`` 按 token / 工具事件逐步产出，
  供 SSE 端点与 Web UI 做进度展示；
- **行程规划**：``plan_trip`` 走 Plan-and-Execute——确定性排程引擎给出
  逐日骨架，结构化输出生成 ``TravelPlan``，Verifier 校验预算算术与
  景点锚定，未通过则带 issues 自纠重试。
"""
import time
from collections.abc import AsyncGenerator
from typing import Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.agents.verifier import verify_plan
from src.config.llm import build_chat_model
from src.config.settings import get_settings, require_api_keys
from src.memory.base import BaseMemory
from src.memory.file_memory import FileMemory
from src.memory.history import build_history_messages
from src.memory.profile import ProfileStore
from src.memory.sqlite_memory import SqliteMemory
from src.models.plan import TravelPlan, TripRequestArgs
from src.planner.budget import estimate_budget
from src.planner.itinerary import build_day_schedule
from src.tools import get_travel_tools
from src.tools.amap.poi import POITool
from src.utils.logger import logger
from src.utils.telemetry import TokenUsageHandler

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

请用友好的语气，内容要具体详实。回答必须以工具返回的真实数据为依据，
不要编造工具结果之外的景点名、价格或营业信息。"""

CHAT_ERROR_FALLBACK = "抱歉，处理您的请求时出错，请稍后重试。"
EMPTY_RESPONSE_FALLBACK = "抱歉，未能生成响应，请换个说法再试。"

PLAN_SYSTEM = """你是行程规划结构化器。基于给定的调研材料与逐日排程骨架，输出符合 TravelPlan schema 的结构化行程。
硬性要求：
1. day_plans[].spots 只能使用给定景点池中的准确名称，不得编造景点；
2. total_estimated_cost 必须精确等于「各日 estimated_cost 之和 + hotel_est_cost_total」；
3. 花费估算需参考给定的确定性预算参考，总估算不得超过用户预算（除非说明原因）；
4. 美食推荐只能来自调研材料中工具查询到的名称。"""

PLAN_USER_TMPL = """【用户需求】
{user_input}

【行程参数】
目的地：{destination}
天数：{days} 天
总预算：{budget} 元

【景点池（事实锚定白名单，只能从中选择）】
{spots_pool}

【逐日排程骨架（由地理就近算法生成，请遵循此顺序安排）】
{schedule_hint}

【确定性预算参考】
{budget_hint}

【调研材料（Agent 工具查询结果）】
{research}

请输出符合 TravelPlan schema 的结构化行程。"""


def _default_memory() -> BaseMemory:
    """按 ``MEMORY_BACKEND`` 配置构建会话记忆后端。"""
    backend = get_settings().MEMORY_BACKEND.strip().lower()
    if backend == "sqlite":
        return SqliteMemory()
    return FileMemory()


class TravelAssistant:
    """智能旅行助手。"""

    def __init__(
        self,
        memory: Optional[BaseMemory] = None,
        history_summarizer: Optional[Callable] = None,
    ):
        # 显式校验 API Key，给出清晰错误而非晦涩的下游异常
        require_api_keys()

        self.tools = get_travel_tools()
        self.llm = self._init_llm()
        self.agent = self._create_agent()
        # 会话记忆：默认按配置选择 file / sqlite；会话持久化 + 用户画像
        self.memory: BaseMemory = memory or _default_memory()
        self.profiles = ProfileStore()
        # 可注入的历史摘要器（LLM 摘要）；None 时退化为规则摘要
        self.history_summarizer = history_summarizer
        # 向量语义记忆（SEMANTIC_MEMORY_ENABLED 开启时启用，默认关闭）
        self.semantic = None
        if get_settings().SEMANTIC_MEMORY_ENABLED:
            from src.memory.semantic import SemanticMemory

            self.semantic = SemanticMemory()

    def _init_llm(self):
        return build_chat_model()

    def _create_agent(self):
        return create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=SystemMessage(content=SYSTEM_PROMPT),
        )

    # ------------------------------------------------------------------
    # 消息构建（chat 与 astream_chat 共用）
    # ------------------------------------------------------------------
    def _build_messages(
        self,
        history_dicts: list,
        user_input: str,
        session_id: str,
        maintain_profile: bool,
    ) -> list:
        """构建本轮发送给 agent 的消息序列。

        顺序：[用户画像 SystemMessage（如有）] + [历史窗口] + [当前输入]。
        """
        s = get_settings()
        messages = build_history_messages(
            history_dicts,
            limit=s.AGENT_HISTORY_LIMIT,
            content_max=s.AGENT_HISTORY_CONTENT_MAX,
            summarizer=self.history_summarizer,
        )

        # 用户画像仅在持久化会话模式下维护与注入（显式传 history 的调用方
        # 自管状态，避免跨会话画像串扰）
        if maintain_profile:
            profile = self.profiles.update_from_text(session_id, user_input)
            profile_block = ProfileStore.render_block(profile)
            if profile_block:
                messages.insert(0, SystemMessage(content=profile_block))

        # 向量语义记忆召回（跨会话的相关历史行程，开启时注入）
        if self.semantic is not None:
            recalled = self.semantic.recall(user_input, k=s.SEMANTIC_MEMORY_TOP_K)
            if recalled:
                lines = "\n".join(f"- {item['text']}" for item in recalled)
                messages.insert(
                    0,
                    SystemMessage(content=f"【相关历史行程记忆】（跨会话语义召回，供参考）\n{lines}"),
                )

        messages.append(HumanMessage(content=user_input))
        return messages

    def _load_history(self, chat_history: Optional[list], session_id: str) -> list:
        """显式传入优先，否则回退到持久化记忆。"""
        if chat_history is not None:
            return chat_history
        return self.memory.get_messages(session_id, limit=0)

    def _persist_turn(self, session_id: str, user_input: str, response: str) -> None:
        self.memory.add_messages(
            session_id,
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": response},
            ],
        )
        # 语义记忆：持久化用户需求原文（开启时），供跨会话召回
        if self.semantic is not None:
            self.semantic.remember(session_id, user_input)

    # ------------------------------------------------------------------
    # 同步对话
    # ------------------------------------------------------------------
    def chat(
        self,
        user_input: str,
        chat_history: Optional[list] = None,
        session_id: str = "default",
    ) -> str:
        """与旅行助手对话（阻塞式）。

        Args:
            user_input: 用户输入。
            chat_history: 对话历史（优先级高于 session_id 持久化记忆），
                格式 ``[{"role": "user"|"assistant", "content": "..."}]``。
                传入 None 时自动从持久化记忆按 session_id 加载，并维护用户画像。
            session_id: 会话标识，用于持久化记忆与画像读写。

        Returns:
            助手回复文本。
        """
        history_dicts = self._load_history(chat_history, session_id)
        messages = self._build_messages(
            history_dicts, user_input, session_id, maintain_profile=chat_history is None
        )

        usage = TokenUsageHandler(session_id=session_id)
        try:
            started = time.monotonic()
            result = self.agent.invoke(
                {"messages": messages},
                config={
                    "recursion_limit": get_settings().AGENT_RECURSION_LIMIT,
                    "callbacks": [usage],
                },
            )
            response = self._extract_response(result)
            usage.log()
            logger.info(
                "Agent 对话完成 session=%s 耗时=%.2fs 输入长度=%d 输出长度=%d",
                session_id,
                time.monotonic() - started,
                len(user_input),
                len(response or ""),
            )
        except Exception as e:
            logger.error("Agent 调用失败: %s", e, exc_info=True)
            return CHAT_ERROR_FALLBACK

        if not response:
            # 无有效 AI 回复：返回兜底文案但不落盘，避免把占位文案当真实回复持久化
            return EMPTY_RESPONSE_FALLBACK

        # 持久化本轮对话（仅当未显式传入 chat_history 时，避免与外部状态重复写入）
        if chat_history is None:
            self._persist_turn(session_id, user_input, response)

        return response

    # ------------------------------------------------------------------
    # 流式对话
    # ------------------------------------------------------------------
    async def astream_chat(
        self,
        user_input: str,
        chat_history: Optional[list] = None,
        session_id: str = "default",
    ) -> AsyncGenerator[dict, None]:
        """流式对话：逐步产出事件供 SSE / Web UI 消费。

        事件格式::

            {"type": "tool_start", "name": "查询实时天气"}
            {"type": "token",     "content": "北京"}
            {"type": "final",     "content": "完整回复文本"}   # 最后一个事件
            {"type": "error",     "message": "用户可读错误"}   # 异常时取代 final

        记忆与画像语义与 :meth:`chat` 完全一致。
        """
        history_dicts = self._load_history(chat_history, session_id)
        messages = self._build_messages(
            history_dicts, user_input, session_id, maintain_profile=chat_history is None
        )

        final_text: Optional[str] = None
        try:
            async for event in self.agent.astream_events(
                {"messages": messages},
                version="v2",
                config={"recursion_limit": get_settings().AGENT_RECURSION_LIMIT},
            ):
                etype = event.get("event")
                if etype == "on_tool_start":
                    yield {"type": "tool_start", "name": event.get("name", "")}
                elif etype == "on_tool_end":
                    yield {"type": "tool_end", "name": event.get("name", "")}
                elif etype == "on_chat_model_stream":
                    chunk = (event.get("data") or {}).get("chunk")
                    content = getattr(chunk, "content", "")
                    if isinstance(content, str) and content:
                        yield {"type": "token", "content": content}
                elif etype == "on_chat_model_end":
                    output = (event.get("data") or {}).get("output")
                    if output is None or getattr(output, "tool_calls", None):
                        continue
                    text = self._content_to_text(getattr(output, "content", ""))
                    if text:
                        final_text = text
        except Exception as e:
            logger.error("Agent 流式调用失败: %s", e, exc_info=True)
            yield {"type": "error", "message": CHAT_ERROR_FALLBACK}
            return

        if not final_text:
            yield {"type": "final", "content": EMPTY_RESPONSE_FALLBACK}
            return

        # 持久化语义与 chat() 一致：显式传 history 的调用方自管状态
        if chat_history is None:
            self._persist_turn(session_id, user_input, final_text)

        yield {"type": "final", "content": final_text}

    # ------------------------------------------------------------------
    # 结果提取
    # ------------------------------------------------------------------
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
        """清空指定会话的会话记忆与用户画像。"""
        self.memory.clear(session_id)
        self.profiles.clear(session_id)

    # ------------------------------------------------------------------
    # 行程规划（Plan-and-Execute）
    # ------------------------------------------------------------------
    def plan_trip(self, user_input: str, session_id: str = "default") -> dict:
        """结构化行程规划：确定性排程 → 调研 → 结构化草稿 → 校验自纠。

        流程（Plan-and-Execute）：
          1. ``with_structured_output`` 抽取参数（目的地/天数/预算）；
          2. 景点池来自高德 POI 真实查询（名称+坐标）；
          3. 排程引擎按就近原则产出逐日骨架（Plan）；
          4. 复用 ReAct Agent 调研（天气/美食/住宿等，Execute）；
          5. ``with_structured_output`` 生成 :class:`TravelPlan` 草稿，
             Verifier 校验预算算术与景点锚定，未通过则带 issues 自纠重试。

        Returns:
            ``{"plan", "verification", "schedule", "params", "budget_floor"}``，
            值均为 pydantic 模型（由 API 层负责 dump）。
        """
        s = get_settings()

        # Step 1: 参数抽取（结构化，而非正则猜测）
        extractor = self.llm.with_structured_output(TripRequestArgs)
        args = extractor.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "从用户输入中抽取行程参数：目的地城市、天数、总预算（元）。" "未提及的字段用默认值：目的地留空、天数 1、预算 0。"
                    ),
                },
                {"role": "user", "content": user_input},
            ]
        )
        destination = (args.destination or "").strip()

        # Step 2: 景点池（真实 API 数据，作为事实锚定白名单 + 排程输入）
        poi_data = (
            POITool.search_scenic_spots(destination, page_size=15)
            if destination
            else None
        )
        pois = (poi_data or {}).get("pois") or []
        allowed_spots = [p["name"] for p in pois if p.get("name")]
        named_coords = [
            (p["name"], p["location"])
            for p in pois
            if p.get("name") and p.get("location")
        ]

        # Step 3: 确定性排程骨架 + 预算参考（不经 LLM）
        schedule = build_day_schedule(named_coords, args.days)
        transit_km = sum(d.est_distance_km for d in schedule)
        budget_floor = estimate_budget(args.days, transit_km_total=transit_km)
        schedule_hint = (
            "\n".join(
                f"  Day{d.day}: {' → '.join(d.spots)}（市内约 {d.est_distance_km} 公里）"
                for d in schedule
            )
            or "  （景点查询无结果，请基于调研材料自行安排，但景点名仍需真实可查）"
        )

        # Step 4: ReAct Agent 调研（天气/美食/住宿等实时信息）
        research = self.chat(user_input, session_id=session_id)

        # Step 5: 结构化草稿 + 校验自纠
        planner = self.llm.with_structured_output(TravelPlan)
        user_prompt = PLAN_USER_TMPL.format(
            user_input=user_input,
            destination=destination or "未提供（请从调研材料推断）",
            days=args.days,
            budget=args.budget or "未提供",
            spots_pool="、".join(allowed_spots) or "（空）",
            schedule_hint=schedule_hint,
            budget_hint=(
                f"餐饮+市内交通确定性估算约 {budget_floor.total:.0f} 元" "（不含住宿与门票，请在此基础上叠加）"
            ),
            research=research,
        )
        messages = [
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        draft = planner.invoke(messages)
        verification = verify_plan(
            draft, allowed_spots=allowed_spots, budget=args.budget
        )
        retries = 0
        while not verification.ok and retries < s.PLAN_VERIFY_RETRIES:
            logger.warning("行程草稿未通过校验（第 %d 次自纠）: %s", retries + 1, verification.issues)
            messages.append({"role": "assistant", "content": draft.model_dump_json()})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "上次草稿未通过校验，请修正以下问题后重新输出完整 JSON：\n- "
                        + "\n- ".join(verification.issues)
                    ),
                }
            )
            draft = planner.invoke(messages)
            verification = verify_plan(
                draft, allowed_spots=allowed_spots, budget=args.budget
            )
            retries += 1

        logger.info(
            "行程规划完成 session=%s destination=%s days=%s ok=%s retries=%d",
            session_id,
            destination,
            args.days,
            verification.ok,
            retries,
        )
        return {
            "plan": draft,
            "verification": verification,
            "schedule": schedule,
            "params": args,
            "budget_floor": budget_floor,
        }

    # ------------------------------------------------------------------
    # 异步对话
    # ------------------------------------------------------------------
    async def achat(
        self,
        user_input: str,
        chat_history: Optional[list] = None,
        session_id: str = "default",
    ) -> str:
        """``chat`` 的异步版本（LangGraph ``ainvoke``，工具在执行器中运行）。

        记忆 / 画像 / 语义召回 / token 观测语义与同步版完全一致。
        """
        history_dicts = self._load_history(chat_history, session_id)
        messages = self._build_messages(
            history_dicts, user_input, session_id, maintain_profile=chat_history is None
        )

        usage = TokenUsageHandler(session_id=session_id)
        try:
            started = time.monotonic()
            result = await self.agent.ainvoke(
                {"messages": messages},
                config={
                    "recursion_limit": get_settings().AGENT_RECURSION_LIMIT,
                    "callbacks": [usage],
                },
            )
            response = self._extract_response(result)
            usage.log()
            logger.info(
                "Agent 异步对话完成 session=%s 耗时=%.2fs 输入长度=%d 输出长度=%d",
                session_id,
                time.monotonic() - started,
                len(user_input),
                len(response or ""),
            )
        except Exception as e:
            logger.error("Agent 异步调用失败: %s", e, exc_info=True)
            return CHAT_ERROR_FALLBACK

        if not response:
            return EMPTY_RESPONSE_FALLBACK

        if chat_history is None:
            self._persist_turn(session_id, user_input, response)
        return response
