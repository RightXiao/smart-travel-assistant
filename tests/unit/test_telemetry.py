"""token 用量回调测试。"""
from src.utils.telemetry import TokenUsageHandler


class _FakeUsage:
    def __init__(self, prompt, completion, total):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class _FakeResponse:
    """模拟 LangChain LLMResult（llm_output.token_usage 为 dict，与真实一致）。"""

    def __init__(self, usage: _FakeUsage):
        self.llm_output = {
            "token_usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        }


class TestTokenUsageHandler:
    def test_accumulates_usage_across_calls(self):
        handler = TokenUsageHandler(session_id="s1")
        handler.on_llm_end(_FakeResponse(_FakeUsage(100, 50, 150)))
        handler.on_llm_end(_FakeResponse(_FakeUsage(200, 80, 280)))
        assert handler.llm_calls == 2
        assert handler.prompt_tokens == 300
        assert handler.completion_tokens == 130
        assert handler.total_tokens == 430

    def test_tolerates_missing_usage_fields(self):
        """用量字段缺失 / 格式异常时静默跳过，不影响主流程。"""

        class _Weird:
            llm_output = {}

        class _Broken:
            llm_output = None

        handler = TokenUsageHandler()
        handler.on_llm_end(_Weird())
        handler.on_llm_end(_Broken())
        assert handler.llm_calls == 2
        assert handler.total_tokens == 0

    def test_summary_and_log(self, caplog):
        import logging

        handler = TokenUsageHandler(session_id="s2")
        handler.on_llm_end(_FakeResponse(_FakeUsage(10, 5, 15)))
        summary = handler.summary()
        assert "session=s2" in summary
        assert "total_tokens=15" in summary
        caplog.set_level(logging.INFO, logger="travel_agent")
        handler.log()
