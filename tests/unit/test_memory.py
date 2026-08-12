"""文件记忆系统测试。

注意：在当前 Windows 环境下 pytest 内置 ``tmp_path`` 因系统 Temp 目录权限
（WinError 5 拒绝访问）无法使用，故改用项目内的 ``tests/.tmp`` 目录，
并在测试结束后统一清理。
"""
import json
import shutil
import threading
from pathlib import Path

import pytest

from src.memory.file_memory import FileMemory

_TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp"


@pytest.fixture
def mem_dir():
    """每个测试一个独立子目录，测试后清理。"""
    _TMP_ROOT.mkdir(exist_ok=True)
    d = Path(_TMP_ROOT) / f"mem_{id(object())}"
    yield str(d)
    if Path(d).exists():
        shutil.rmtree(d, ignore_errors=True)


class TestFileMemory:
    """覆盖 TravelAssistant 现已接入的持久化逻辑。"""

    def test_add_and_get(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_message("s1", {"role": "user", "content": "你好"})
        mem.add_message("s1", {"role": "assistant", "content": "你好！"})
        msgs = mem.get_messages("s1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["content"] == "你好！"

    def test_add_messages_batch(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_messages("s1", [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ])
        assert len(mem.get_messages("s1")) == 2

    def test_limit_returns_recent(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        for i in range(5):
            mem.add_message("s1", {"role": "user", "content": str(i)})
        # limit=3 -> 返回最近 3 条
        msgs = mem.get_messages("s1", limit=3)
        assert [m["content"] for m in msgs] == ["2", "3", "4"]

    def test_clear(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_message("s1", {"role": "user", "content": "x"})
        mem.clear("s1")
        assert mem.get_messages("s1") == []

    def test_missing_session_returns_empty(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        assert mem.get_messages("nope") == []

    def test_unsafe_session_id_sanitized(self, mem_dir):
        """含路径分隔符的 session_id 必须被净化，防止目录穿越。"""
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_message("../etc/passwd", {"role": "user", "content": "x"})
        # 仍可读回（落到 storage_dir 内的净化文件）
        assert mem.get_messages("../etc/passwd") != []
        # 不会在上级创建 etc/passwd.json
        assert not (Path(mem_dir).parent / "etc" / "passwd.json").exists()

    def test_list_sessions(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_message("alpha", {"role": "user", "content": "x"})
        mem.add_message("beta", {"role": "user", "content": "y"})
        sessions = mem.list_sessions()
        assert "alpha" in sessions and "beta" in sessions

    def test_distinct_session_ids_no_collision(self, mem_dir):
        """不同原始 id（含易清洗碰撞字符）应映射到不同文件。"""
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_message("a/b", {"role": "user", "content": "1"})
        mem.add_message("a.b", {"role": "user", "content": "2"})
        mem.add_message("a-b", {"role": "user", "content": "3"})
        sessions = mem.list_sessions()
        assert sorted(sessions) == ["a-b", "a.b", "a/b"]
        # 三者互不影响
        assert mem.get_messages("a/b")[0]["content"] == "1"
        assert mem.get_messages("a.b")[0]["content"] == "2"
        assert mem.get_messages("a-b")[0]["content"] == "3"

    def test_empty_session_id_falls_back_to_default(self, mem_dir):
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_message("", {"role": "user", "content": "x"})
        assert mem.get_messages("")[0]["content"] == "x"

    def test_concurrent_adds_no_loss(self, mem_dir):
        """并发追加不应丢失消息（进程内锁保护读-改-写）。"""
        mem = FileMemory(storage_dir=mem_dir)

        def _add(i):
            mem.add_message("s1", {"role": "user", "content": str(i)})

        threads = [threading.Thread(target=_add, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        msgs = mem.get_messages("s1", limit=10_000)
        assert len(msgs) == 50

    def test_atomic_write_leaves_valid_json(self, mem_dir):
        """写入后文件应是合法 JSON，且无 .tmp 残留。"""
        mem = FileMemory(storage_dir=mem_dir)
        mem.add_messages("s1", [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ])
        files = list(Path(mem_dir).glob("*.json"))
        assert len(files) == 1
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert payload["messages"][-1]["content"] == "b"
        assert not list(Path(mem_dir).glob("*.tmp"))
