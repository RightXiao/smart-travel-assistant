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
        with patch("src.agents.travel_assistant.require_api_keys"), \
             patch("src.agents.travel_assistant.ChatOpenAI"), \
             patch("src.agents.travel_assistant.create_react_agent"):
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
