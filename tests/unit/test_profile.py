"""用户偏好画像测试。"""
import json

from src.memory.profile import ProfileStore, extract_preferences


class TestExtractPreferences:
    def test_extracts_city_days_budget(self):
        prefs = extract_preferences("我想去北京旅游3天，预算5000元")
        assert prefs["city"] == "北京"
        assert prefs["days"] == 3
        assert prefs["budget"] == 5000

    def test_extracts_preference_keywords(self):
        prefs = extract_preferences("喜欢历史文化，想拍照打卡，带孩子")
        assert set(prefs["preferences"]) == {"历史文化", "摄影出片", "亲子游"}

    def test_no_match_returns_empty(self):
        assert extract_preferences("你好") == {}
        assert extract_preferences("") == {}

    def test_days_range_guard(self):
        assert "days" not in extract_preferences("去玩99天")
        assert "days" not in extract_preferences("去玩0天")

    def test_budget_range_guard(self):
        assert "budget" not in extract_preferences("预算50元")


class TestProfileStore:
    def test_update_and_get(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        profile = store.update_from_text("s1", "我想去杭州玩2天，预算3000元，喜欢自然风光")
        assert profile["city"] == "杭州"
        assert profile["days"] == 2
        assert profile["budget"] == 3000
        assert "自然风光" in profile["preferences"]
        # 持久化验证
        store2 = ProfileStore(storage_dir=str(tmp_path))
        assert store2.get("s1")["city"] == "杭州"

    def test_preferences_accumulate_not_overwrite(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        store.update_from_text("s1", "喜欢美食")
        profile = store.update_from_text("s1", "也喜欢历史和博物馆")
        assert "美食探索" in profile["preferences"]
        assert "历史文化" in profile["preferences"]

    def test_scalar_fields_override(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        store.update_from_text("s1", "我想去北京旅游3天，预算5000元")
        profile = store.update_from_text("s1", "改成去上海玩5天")
        assert profile["city"] == "上海"
        assert profile["days"] == 5

    def test_no_match_keeps_profile(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        store.update_from_text("s1", "我想去北京")
        profile = store.update_from_text("s1", "嗯嗯好的")
        assert profile["city"] == "北京"

    def test_clear(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        store.update_from_text("s1", "我想去北京")
        store.clear("s1")
        assert store.get("s1") == {}

    def test_corrupted_file_returns_empty(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        store.update_from_text("s1", "我想去北京")
        # 写坏 JSON
        path = next(tmp_path.joinpath("profiles").glob("*.json"))
        path.write_text("{broken", encoding="utf-8")
        assert store.get("s1") == {}

    def test_render_block(self):
        block = ProfileStore.render_block(
            {"city": "北京", "days": 3, "budget": 5000, "preferences": ["美食探索"]}
        )
        assert "【用户画像】" in block
        assert "北京" in block and "5000" in block and "美食探索" in block
        assert ProfileStore.render_block({}) == ""

    def test_storage_format(self, tmp_path):
        store = ProfileStore(storage_dir=str(tmp_path))
        store.update_from_text("会话甲", "我想去北京")
        files = list(tmp_path.joinpath("profiles").glob("*.json"))
        assert len(files) == 1
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert payload["city"] == "北京"
