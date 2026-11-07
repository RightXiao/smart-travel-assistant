"""历史窗口构建测试。"""
from langchain_core.messages import HumanMessage, SystemMessage

from src.memory.history import build_history_messages


def _history(n):
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
        for i in range(n)
    ]


class TestBuildHistoryMessages:
    def test_within_limit_all_kept(self):
        messages = build_history_messages(_history(6), limit=8)
        assert len(messages) == 6
        assert all(isinstance(m, HumanMessage) for m in messages[::2])

    def test_over_limit_truncates_tail_window(self):
        messages = build_history_messages(_history(20), limit=8)
        # 8 条近期消息 + 1 条历史摘要
        assert len(messages) == 9
        assert messages[-1].content == "msg19"

    def test_rule_digest_by_default(self):
        """无 summarizer 时默认注入规则摘要，保留更早对话的关键约束。"""
        messages = build_history_messages(_history(20), limit=8)
        assert isinstance(messages[0], SystemMessage)
        assert "历史摘要" in messages[0].content
        assert "msg0" in messages[0].content

    def test_summarizer_overrides_rule_digest(self):
        messages = build_history_messages(
            _history(20), limit=8, summarizer=lambda older: "用户此前询问了北京行程"
        )
        assert isinstance(messages[0], SystemMessage)
        assert "北京行程" in messages[0].content
        assert "msg0" not in messages[0].content
        assert len(messages) == 9

    def test_content_max_truncation(self):
        history = [{"role": "user", "content": "长" * 1000}]
        messages = build_history_messages(history, limit=8, content_max=100)
        assert len(messages[0].content) == 100

    def test_non_user_assistant_roles_skipped(self):
        history = [
            {"role": "system", "content": "注入"},
            {"role": "user", "content": "hi"},
        ]
        messages = build_history_messages(history, limit=8)
        assert len(messages) == 1
        assert messages[0].content == "hi"

    def test_empty_digest_not_injected(self):
        messages = build_history_messages(
            _history(20), limit=8, summarizer=lambda older: ""
        )
        assert len(messages) == 8
