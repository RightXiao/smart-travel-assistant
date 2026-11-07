"""SQLite 记忆后端测试。"""
import pytest

from src.memory.sqlite_memory import SqliteMemory


@pytest.fixture
def mem(tmp_path):
    return SqliteMemory(db_path=str(tmp_path / "sessions.db"))


class TestSqliteMemory:
    def test_add_and_get(self, mem):
        mem.add_message("s1", {"role": "user", "content": "你好"})
        mem.add_messages("s1", [{"role": "assistant", "content": "你好呀"}])
        msgs = mem.get_messages("s1")
        assert len(msgs) == 2
        assert msgs[0]["content"] == "你好"

    def test_limit(self, mem):
        for i in range(10):
            mem.add_message("s1", {"role": "user", "content": f"m{i}"})
        assert len(mem.get_messages("s1", limit=3)) == 3
        assert mem.get_messages("s1", limit=3)[0]["content"] == "m7"

    def test_sessions_isolated(self, mem):
        mem.add_message("a", {"role": "user", "content": "A"})
        mem.add_message("b", {"role": "user", "content": "B"})
        assert mem.get_messages("a")[0]["content"] == "A"
        assert len(mem.get_messages("b")) == 1

    def test_clear(self, mem):
        mem.add_message("s1", {"role": "user", "content": "x"})
        mem.clear("s1")
        assert mem.get_messages("s1") == []

    def test_list_sessions_sorted(self, mem):
        mem.add_message("b", {"role": "user", "content": "x"})
        mem.add_message("a", {"role": "user", "content": "x"})
        assert mem.list_sessions() == ["a", "b"]

    def test_empty_batch_noop(self, mem):
        mem.add_messages("s1", [])
        assert mem.get_messages("s1") == []

    def test_missing_session(self, mem):
        assert mem.get_messages("nope") == []

    def test_persistence_across_instances(self, tmp_path):
        db = str(tmp_path / "p.db")
        m1 = SqliteMemory(db_path=db)
        m1.add_message("s1", {"role": "user", "content": "持久化"})
        m2 = SqliteMemory(db_path=db)
        assert m2.get_messages("s1")[0]["content"] == "持久化"
