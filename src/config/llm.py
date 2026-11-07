"""LLM 客户端工厂：基于 ``resolve_llm_config`` 统一构建，多厂商接入的唯一入口。

各主流厂商（智谱/DeepSeek/通义/Kimi/OpenAI/Ollama/自建）均提供 OpenAI 兼容
端点，因此统一用 ``ChatOpenAI`` 客户端，仅按厂商解析 ``base_url`` / ``model`` /
``api_key``（见 ``src/config/settings.py::resolve_llm_config``）。
新增厂商只需在 ``LLM_PRESETS`` 增加预设，无需改本模块。
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from src.config.settings import (
    get_settings,
    resolve_embedding_model,
    resolve_llm_config,
)


def build_chat_model(
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
    streaming: bool = False,
) -> ChatOpenAI:
    """按当前多厂商配置构建 Chat 模型客户端。

    Args:
        temperature / max_tokens / timeout / max_retries: 缺省时取 Settings
            对应项（``AGENT_TEMPERATURE`` / ``AGENT_MAX_TOKENS`` / ...）。
        streaming: 是否流式（SSE 路径使用）。
    """
    s = get_settings()
    cfg = resolve_llm_config()
    # ollama 等本地服务可无密钥：OpenAI 客户端要求非空，用占位符
    return ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["api_key"] or "EMPTY",
        base_url=cfg["base_url"],
        temperature=s.AGENT_TEMPERATURE if temperature is None else temperature,
        max_tokens=s.AGENT_MAX_TOKENS if max_tokens is None else max_tokens,
        timeout=s.LLM_TIMEOUT if timeout is None else timeout,
        max_retries=s.LLM_MAX_RETRIES if max_retries is None else max_retries,
        streaming=streaming,
    )


def build_embedding_client():
    """按当前多厂商配置构建 embeddings 客户端（语义记忆用）。"""
    from langchain_openai import OpenAIEmbeddings

    cfg = resolve_llm_config()
    return OpenAIEmbeddings(
        model=resolve_embedding_model(),
        api_key=cfg["api_key"] or "EMPTY",
        base_url=cfg["base_url"],
        check_embedding_ctx_length=False,
    )
