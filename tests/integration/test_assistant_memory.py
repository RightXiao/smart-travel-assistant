"""集成测试：TravelAssistant 的 FileMemory 接入。

不依赖真实 LLM / 网络，通过 mock agent.invoke 验证：
1. 首次对话后历史被持久化；
2. 再次对话（不显式传 history）能自动加载上一轮历史并传入 agent。

注意：当前 Windows 环境下 pytest 内置 ``tmp_path`` 因系统 Temp 目录权限
（WinError 5）不可用，故改用项目内 ``tests/.tmp`` 目录。
"""
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.travel_assistant import TravelAssistant
from src.memory.file_memory import FileMemory

_TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp"


@pytest.fixture
def mem_dir():
    _TMP_ROOT.mkdir(exist_ok=True)
    d = Path(_TMP_ROOT) / f"asst_{id(object())}"
    yield d
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def _build_assistant(mem_dir: Path):
    """构造一个绕过真实 LLM 初始化的 TravelAssistant。"""
    with patch("src.agents.travel_assistant.require_api_keys"), \
         patch("src.agents.travel_assistant.ChatOpenAI"), \
         patch("src.agents.travel_assistant.create_react_agent"):
        asst = TravelAssistant(memory=FileMemory(storage_dir=str(mem_dir)))
    return asst


def _fake_invoke(captured):
    """返回一个会记录入参 messages 的 fake agent.invoke。"""

    def _invoke(payload):
        captured["last_messages"] = payload["messages"]
        return {"messages": [AIMessage(content="这是助手回复")]}

    return _invoke


class TestAssistantMemory:
    def test_history_persisted_after_chat(self, mem_dir):
        asst = _build_assistant(mem_dir)
        asst.agent.invoke = MagicMock(side_effect=_fake_invoke({"last_messages": []}))

        resp = asst.chat("我想去北京", session_id="u1")
        assert resp == "这是助手回复"

        # 会话文件名为 sha256 摘要，这里通过 list_sessions 定位
        assert asst.memory.list_sessions() == ["u1"]
        files = list(mem_dir.glob("*.json"))
        assert len(files) == 1
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        msgs = payload["messages"]
        assert len(msgs) == 2
        assert msgs[0]["content"] == "我想去北京"
        assert msgs[1]["role"] == "assistant"

    def test_history_auto_loaded_next_turn(self, mem_dir):
        asst = _build_assistant(mem_dir)
        captured = {}
        asst.agent.invoke = MagicMock(side_effect=_fake_invoke(captured))

        asst.chat("我想去北京，预算5000", session_id="u1")
        captured.clear()
        asst.chat("那上海呢？", session_id="u1")

        # 第二轮传入 agent 的 messages 应包含上一轮历史（HumanMessage + AIMessage）
        sent = captured["last_messages"]
        # 最后一条是当前用户输入
        assert "那上海呢？" in sent[-1].content
        # 历史里应能找到上一轮的北京相关消息
        joined = "".join(getattr(m, "content", "") for m in sent)
        assert "北京" in joined

    def test_explicit_history_overrides_persistence(self, mem_dir):
        asst = _build_assistant(mem_dir)
        captured = {}
        asst.agent.invoke = MagicMock(side_effect=_fake_invoke(captured))

        asst.chat("想去看海", session_id="u1")
        captured.clear()
        # 显式传入 history -> 不读持久化，且本轮不回写
        asst.chat(
            "换个话题",
            chat_history=[{"role": "user", "content": "外部历史"}],
            session_id="u1",
        )
        joined = "".join(getattr(m, "content", "") for m in captured["last_messages"])
        assert "外部历史" in joined

    def test_clear_memory(self, mem_dir):
        asst = _build_assistant(mem_dir)
        asst.agent.invoke = MagicMock(side_effect=_fake_invoke({}))
        asst.chat("hi", session_id="u1")
        assert asst.memory.list_sessions() == ["u1"]
        asst.clear_memory("u1")
        assert asst.memory.list_sessions() == []
