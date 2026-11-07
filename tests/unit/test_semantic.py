"""向量语义记忆测试（注入确定性 embedder，不调 API）。"""
import pytest

from src.memory.semantic import SemanticMemory, _cosine


def _fake_embedder_factory(dim=8):
    """确定性伪 embedder：按关键词映射到单位向量（可控制相似度）。"""

    def embed(text: str):
        vec = [0.0] * dim
        mapping = {"杭州": 0, "北京": 1, "美食": 2, "亲子": 3, "徒步": 4}
        for kw, idx in mapping.items():
            if kw in text:
                vec[idx] = 1.0
        # 无命中时给一个固定基向量，避免零向量
        if all(v == 0 for v in vec):
            vec[dim - 1] = 1.0
        return vec

    return embed


@pytest.fixture
def mem(tmp_path):
    return SemanticMemory(storage_dir=str(tmp_path), embedder=_fake_embedder_factory())


class TestCosine:
    def test_identical_vectors(self):
        assert _cosine([1, 0], [1, 0]) == 1.0

    def test_orthogonal(self):
        assert _cosine([1, 0], [0, 1]) == 0.0

    def test_zero_vector(self):
        assert _cosine([0, 0], [1, 0]) == 0.0

    def test_mismatched_dims(self):
        assert _cosine([1], [1, 0]) == 0.0


class TestSemanticMemory:
    def test_remember_and_recall(self, mem):
        mem.remember("s1", "我想去杭州玩，喜欢美食")
        mem.remember("s2", "北京亲子游攻略")
        results = mem.recall("杭州 美食 行程", k=2)
        assert len(results) == 1  # 只有杭州那条相似度 > 0
        assert "杭州" in results[0]["text"]
        assert results[0]["session_id"] == "s1"

    def test_ranking_by_similarity(self, mem):
        mem.remember("s1", "北京旅游")
        mem.remember("s1", "杭州美食之旅")
        results = mem.recall("北京 行程", k=2)
        assert results[0]["text"] == "北京旅游"

    def test_top_k_limit(self, mem):
        for i in range(6):
            mem.remember("s1", f"杭州美食行程{i}")
        results = mem.recall("杭州美食", k=3)
        assert len(results) == 3

    def test_session_filter(self, mem):
        mem.remember("s1", "杭州美食之旅")
        mem.remember("s2", "杭州美食之旅二")
        results = mem.recall("杭州美食", k=5, session_id="s1")
        assert all(r["session_id"] == "s1" for r in results)

    def test_empty_text_noop(self, mem):
        mem.remember("s1", "  ")
        assert mem._load() == []
        assert mem.recall("") == []

    def test_fifo_eviction(self, tmp_path):
        from src.config.settings import get_settings

        max_entries = get_settings().SEMANTIC_MEMORY_MAX_ENTRIES
        mem = SemanticMemory(
            storage_dir=str(tmp_path), embedder=_fake_embedder_factory()
        )
        for i in range(max_entries + 10):
            mem.remember("s1", f"杭州美食行程{i}")
        entries = mem._load()
        assert len(entries) == max_entries
        # 最早的 10 条被淘汰
        assert "杭州美食行程0" not in [e["text"] for e in entries[:12]]

    def test_persistence_across_instances(self, tmp_path):
        m1 = SemanticMemory(
            storage_dir=str(tmp_path), embedder=_fake_embedder_factory()
        )
        m1.remember("s1", "杭州美食之旅")
        m2 = SemanticMemory(
            storage_dir=str(tmp_path), embedder=_fake_embedder_factory()
        )
        assert m2.recall("杭州美食", k=1)[0]["text"] == "杭州美食之旅"

    def test_clear(self, mem):
        mem.remember("s1", "杭州美食之旅")
        mem.clear()
        assert mem.recall("杭州美食") == []

    def test_corrupted_file_returns_empty(self, tmp_path):
        mem = SemanticMemory(
            storage_dir=str(tmp_path), embedder=_fake_embedder_factory()
        )
        mem.remember("s1", "杭州美食之旅")
        mem._path.write_text("{broken", encoding="utf-8")
        assert mem._load() == []
        assert mem.recall("杭州美食") == []
