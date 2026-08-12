import time
from unittest.mock import MagicMock, patch

from src.utils import http


class TestTTLCache:
    def test_set_and_get(self):
        cache = http.TTLCache()
        cache.set("k", {"v": 1}, ttl=10)
        assert cache.get("k") == {"v": 1}

    def test_expired_returns_none(self):
        cache = http.TTLCache()
        cache.set("k", "v", ttl=0)
        time.sleep(0.01)
        assert cache.get("k") is None

    def test_missing_key_returns_none(self):
        cache = http.TTLCache()
        assert cache.get("absent") is None

    def test_clear(self):
        cache = http.TTLCache()
        cache.set("k", "v", ttl=10)
        cache.clear()
        assert cache.get("k") is None


class TestCachedJsonGet:
    def test_returns_json_on_success(self, mock_env_vars):
        with patch("src.utils.http.get_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"status": "1", "ok": True}
            mock_resp.raise_for_status.return_value = None
            mock_session.return_value.get.return_value = mock_resp

            http.clear_cache()
            data = http.cached_json_get("http://x", {"a": 1}, cache_key="key1")
            assert data == {"status": "1", "ok": True}

    def test_caches_result(self, mock_env_vars):
        """相同 cache_key 第二次不发起请求。"""
        with patch("src.utils.http.get_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"status": "1"}
            mock_resp.raise_for_status.return_value = None
            mock_session.return_value.get.return_value = mock_resp

            http.clear_cache()
            http.cached_json_get("http://x", {"a": 1}, cache_key="key2")
            http.cached_json_get("http://x", {"a": 1}, cache_key="key2")
            assert mock_session.return_value.get.call_count == 1

    def test_returns_none_on_request_exception(self, mock_env_vars):
        import requests

        with patch("src.utils.http.get_session") as mock_session:
            mock_session.return_value.get.side_effect = requests.RequestException("boom")
            http.clear_cache()
            assert http.cached_json_get("http://x", {}, cache_key="k") is None

    def test_error_response_not_cached(self, mock_env_vars):
        """高德错误体（status=="0"）不应被缓存，否则 API 恢复后仍持续失败。"""
        with patch("src.utils.http.get_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            # 第一次返回错误体，第二次返回成功体
            mock_resp.json.side_effect = [
                {"status": "0", "info": "临时错误"},
                {"status": "1", "data": "ok"},
            ]
            mock_session.return_value.get.return_value = mock_resp

            http.clear_cache()
            first = http.cached_json_get("http://x", {"a": 1}, cache_key="k")
            second = http.cached_json_get("http://x", {"a": 1}, cache_key="k")

            assert first == {"status": "0", "info": "临时错误"}
            # 错误体未被缓存，第二次仍发起请求并拿到成功结果
            assert second == {"status": "1", "data": "ok"}
            assert mock_session.return_value.get.call_count == 2

    def test_non_dict_response_not_cached(self, mock_env_vars):
        """非 dict 响应不应触发缓存写（避免后续 .get() 失败）。"""
        with patch("src.utils.http.get_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = ["not", "a", "dict"]
            mock_session.return_value.get.return_value = mock_resp

            http.clear_cache()
            data = http.cached_json_get("http://x", {}, cache_key="k")
            assert data == ["not", "a", "dict"]
            # 第二次调用仍会发请求（未缓存）
            http.cached_json_get("http://x", {}, cache_key="k")
            assert mock_session.return_value.get.call_count == 2
