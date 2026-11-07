"""LLM token 用量观测：LangChain 回调处理器。

每次 ``chat`` 创建独立 handler 挂到 ``agent.invoke`` 的 ``callbacks``，
调用结束后记录本轮 prompt / completion / 总 token 数与 LLM 调用次数，
为成本核算与容量评估提供数据（后续可无缝接 Prometheus / LangSmith）。
"""
from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from src.utils.logger import logger


class TokenUsageHandler(BaseCallbackHandler):
    """按轮次累计 token 用量的回调处理器。"""

    def __init__(self, session_id: str = "default") -> None:
        self.session_id = session_id
        self.llm_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """``LLMResult`` 结束时提取 token 用量（OpenAI 兼容格式优先）。"""
        self.llm_calls += 1
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            usage = llm_output.get("token_usage") or {}
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            self.total_tokens += int(usage.get("total_tokens") or 0)
        except (TypeError, ValueError, AttributeError):
            # 用量字段缺失 / 格式不符时静默跳过，不影响主流程
            pass

    def summary(self) -> str:
        """返回本轮回调的用量摘要（供日志输出）。"""
        return (
            f"session={self.session_id} llm_calls={self.llm_calls} "
            f"prompt_tokens={self.prompt_tokens} "
            f"completion_tokens={self.completion_tokens} "
            f"total_tokens={self.total_tokens}"
        )

    def log(self) -> None:
        logger.info("LLM token 用量 %s", self.summary())
