"""``astream_chat`` 流式事件测试（mock agent.astream_events）。"""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from src.agents.travel_assistant import TravelAssistant
from src.memory.file_memory import FileMemory

_TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp"


@pytest.fixture
def mem_dir():
    _TMP_ROOT.mkdir(exist_ok=True)
    d = Path(_TMP_ROOT) / f"stream_{id(object())}"
    yield d
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def _build(mem_dir):
    with patch("src.agents.travel_assistant.require_api_keys"), patch(
        "src.agents.travel_assistant.build_chat_model"
    ), patch("src.agents.travel_assistant.create_react_agent"):
        return TravelAssistant(memory=FileMemory(storage_dir=str(mem_dir)))


def _fake_astream_events(events):
    async def _gen(payload, version=None, config=None):
        for ev in events:
            yield ev

    return _gen


def _run(agen):
    async def _collect():
        return [ev async for ev in agen]

    return asyncio.run(_collect())


class TestAStreamChat:
    def test_yields_tool_and_final_events(self, mem_dir):
        asst = _build(mem_dir)
        asst.agent.astream_events = MagicMock(
            side_effect=_fake_astream_events(
                [
                    {"event": "on_tool_start", "name": "查询实时天气"},
                    {"event": "on_tool_end", "name": "查询实时天气"},
                    {
                        "event": "on_chat_model_stream",
                        "data": {"chunk": AIMessageChunk(content="北京")},
                    },
                    {
                        "event": "on_chat_model_end",
                        "data": {"output": AIMessage(content="北京天气不错")},
                    },
                ]
            )
        )
        events = _run(asst.astream_chat("北京天气", session_id="u1"))
        types = [e["type"] for e in events]
        assert types == ["tool_start", "tool_end", "token", "final"]
        assert events[0]["name"] == "查询实时天气"
        assert events[2]["content"] == "北京"
        assert events[3]["content"] == "北京天气不错"

    def test_final_persists_turn(self, mem_dir):
        asst = _build(mem_dir)
        asst.agent.astream_events = MagicMock(
            side_effect=_fake_astream_events(
                [
                    {
                        "event": "on_chat_model_end",
                        "data": {"output": AIMessage(content="最终回复")},
                    }
                ]
            )
        )
        _run(asst.astream_chat("hi", session_id="u1"))
        msgs = asst.memory.get_messages("u1")
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[1]["content"] == "最终回复"

    def test_intermediate_model_end_with_tool_calls_ignored(self, mem_dir):
        """带 tool_calls 的中间模型输出不作为 final。"""
        asst = _build(mem_dir)
        intermediate = AIMessage(
            content="",
            tool_calls=[{"name": "查询实时天气", "args": {"city": "北京"}, "id": "call_1"}],
        )
        asst.agent.astream_events = MagicMock(
            side_effect=_fake_astream_events(
                [
                    {"event": "on_chat_model_end", "data": {"output": intermediate}},
                    {
                        "event": "on_chat_model_end",
                        "data": {"output": AIMessage(content="真正的最终回复")},
                    },
                ]
            )
        )
        events = _run(asst.astream_chat("hi", session_id="u1"))
        finals = [e for e in events if e["type"] == "final"]
        assert len(finals) == 1
        assert finals[0]["content"] == "真正的最终回复"

    def test_error_event_on_exception(self, mem_dir):
        asst = _build(mem_dir)

        async def _boom(payload, version=None, config=None):
            raise RuntimeError("boom-secret")
            yield  # pragma: no cover

        asst.agent.astream_events = MagicMock(side_effect=_boom)
        events = _run(asst.astream_chat("hi", session_id="u1"))
        assert events == [{"type": "error", "message": events[0]["message"]}]
        assert "boom-secret" not in events[0]["message"]
        # 失败轮次不落盘
        assert asst.memory.get_messages("u1") == []

    def test_empty_response_fallback_not_persisted(self, mem_dir):
        asst = _build(mem_dir)
        asst.agent.astream_events = MagicMock(
            side_effect=_fake_astream_events(
                [
                    {
                        "event": "on_chat_model_end",
                        "data": {"output": AIMessage(content="")},
                    }
                ]
            )
        )
        events = _run(asst.astream_chat("hi", session_id="u1"))
        assert events[-1]["type"] == "final"
        assert "未能生成响应" in events[-1]["content"]
        assert asst.memory.get_messages("u1") == []

    def test_explicit_history_not_persisted(self, mem_dir):
        asst = _build(mem_dir)
        asst.agent.astream_events = MagicMock(
            side_effect=_fake_astream_events(
                [
                    {
                        "event": "on_chat_model_end",
                        "data": {"output": AIMessage(content="回复")},
                    }
                ]
            )
        )
        history = [{"role": "user", "content": "外部历史"}]
        _run(asst.astream_chat("hi", chat_history=history, session_id="u1"))
        assert asst.memory.get_messages("u1") == []
