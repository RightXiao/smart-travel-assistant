import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.travel_assistant import TravelAssistant

_TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp"


@pytest.fixture
def mem_dir():
    _TMP_ROOT.mkdir(exist_ok=True)
    d = Path(_TMP_ROOT) / f"asst_{id(object())}"
    yield d
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


class TestExtractResponse:
    def test_extract_str_content(self):
        result = {"messages": [AIMessage(content="你好，这是回复")]}
        assert TravelAssistant._extract_response(result) == "你好，这是回复"

    def test_extract_content_blocks(self):
        """content 为内容块 list 时应拼接 text 字段。"""
        content = [
            {"type": "text", "text": "第一段"},
            {"type": "text", "text": "第二段"},
        ]
        result = {"messages": [AIMessage(content=content)]}
        assert TravelAssistant._extract_response(result) == "第一段第二段"

    def test_extract_empty_returns_none(self):
        result = {"messages": [AIMessage(content="")]}
        assert TravelAssistant._extract_response(result) is None

    def test_extract_no_ai_message_returns_none(self):
        result = {"messages": []}
        assert TravelAssistant._extract_response(result) is None

    def test_content_to_text_str_and_list(self):
        assert TravelAssistant._content_to_text("abc") == "abc"
        assert TravelAssistant._content_to_text([{"type": "text", "text": "x"}]) == "x"
        assert TravelAssistant._content_to_text(None) == ""


class TestChatErrorSanitization:
    def _build(self, mem_dir):
        with patch("src.agents.travel_assistant.require_api_keys"), patch(
            "src.agents.travel_assistant.build_chat_model"
        ), patch("src.agents.travel_assistant.create_react_agent"):
            from src.memory.file_memory import FileMemory

            return TravelAssistant(memory=FileMemory(storage_dir=str(mem_dir)))

    def test_chat_agent_exception_sanitized(self, mem_dir):
        asst = self._build(mem_dir)
        asst.agent.invoke = MagicMock(side_effect=Exception("leak-my-secret-key-123"))
        resp = asst.chat("hi", session_id="u1")
        # 内部异常信息不得泄漏给用户
        assert "leak-my-secret-key" not in resp
        assert "稍后重试" in resp

    def test_chat_fallback_not_persisted(self, mem_dir):
        """无有效 AI 回复时，不应把占位文案写入记忆。"""
        asst = self._build(mem_dir)
        asst.agent.invoke = MagicMock(return_value={"messages": []})
        resp = asst.chat("hi", session_id="u1")
        assert "未能生成响应" in resp
        assert asst.memory.get_messages("u1") == []

    def test_chat_passes_recursion_limit(self, mem_dir):
        """invoke 应携带来自 Settings 的 recursion_limit，防止 ReAct 循环失控。"""
        asst = self._build(mem_dir)
        captured = {}

        def fake_invoke(payload, config=None):
            captured["config"] = config
            return {"messages": [AIMessage(content="好的")]}

        asst.agent.invoke = MagicMock(side_effect=fake_invoke)
        resp = asst.chat("hi", session_id="u1")
        assert resp == "好的"

        from src.config.settings import get_settings
        from src.utils.telemetry import TokenUsageHandler

        expected = get_settings().AGENT_RECURSION_LIMIT
        assert captured["config"]["recursion_limit"] == expected
        callbacks = captured["config"]["callbacks"]
        assert any(isinstance(cb, TokenUsageHandler) for cb in callbacks)


class TestSemanticMemoryWiring:
    def test_semantic_recall_injected_and_remembered(self, mem_dir):
        """开启语义记忆后：本轮记住用户输入，下轮召回注入 SystemMessage。"""
        from langchain_core.messages import SystemMessage

        from src.memory.semantic import SemanticMemory

        asst = TestChatErrorSanitization._build(self, mem_dir)
        asst.semantic = SemanticMemory(
            storage_dir=str(mem_dir / "semantic"),
            embedder=lambda text: [1.0, 0.0],  # 确定性向量：任何查询都能召回
        )
        captured = {}

        def fake_invoke(payload, config=None):
            captured.setdefault("turns", []).append(payload["messages"])
            return {"messages": [AIMessage(content="好的")]}

        asst.agent.invoke = MagicMock(side_effect=fake_invoke)
        asst.chat("我想去杭州玩", session_id="u1")
        asst.chat("再推荐一下", session_id="u1")

        second_turn = captured["turns"][1]
        assert any(
            isinstance(m, SystemMessage) and "相关历史行程记忆" in m.content
            for m in second_turn
        )
        # 记忆条目已持久化
        assert len(asst.semantic._load()) >= 1

    def test_semantic_disabled_by_default(self, mem_dir):
        """默认关闭：不构建语义记忆、不注入召回块。"""
        asst = TestChatErrorSanitization._build(self, mem_dir)
        assert asst.semantic is None
        captured = {}

        def fake_invoke(payload, config=None):
            captured["messages"] = payload["messages"]
            return {"messages": [AIMessage(content="好的")]}

        asst.agent.invoke = MagicMock(side_effect=fake_invoke)
        asst.chat("hi", session_id="u1")
        assert not any(
            "相关历史行程记忆" in getattr(m, "content", "") for m in captured["messages"]
        )
