from unittest.mock import patch

from src.tools.amap import geocode


class TestGeocode:
    """地理编码工具测试。"""

    def test_geocode_success(self, mock_http):
        """地名 -> 坐标 转换成功。"""
        mock_http(
            {
                "status": "1",
                "geocodes": [
                    {"location": "116.397428,39.90923", "formatted_address": "北京市东城区故宫博物院"}
                ],
            }
        )
        result = geocode.geocode("故宫", city="北京")
        assert result == "116.397428,39.90923"

    def test_geocode_empty_address(self):
        """空地址返回 None（不发请求）。"""
        with patch("src.tools.amap.geocode.cached_json_get") as mock_get:
            assert geocode.geocode("") is None
            assert geocode.geocode("   ") is None
            mock_get.assert_not_called()

    def test_geocode_api_error(self, mock_http):
        """API 返回错误状态时返回 None。"""
        mock_http({"status": "0", "info": "INVALID_USER_KEY"})
        assert geocode.geocode("故宫") is None

    def test_geocode_no_result(self, mock_http):
        """无 geocodes 结果时返回 None。"""
        mock_http({"status": "1", "geocodes": []})
        assert geocode.geocode("火星市") is None

    def test_geocode_or_raw_fallback(self, mock_http):
        """解析失败时原样返回输入。"""
        mock_http({"status": "0"})
        assert geocode.geocode_or_raw("某地") == "某地"

    def test_geocode_or_raw_keeps_coord_input(self, mock_http):
        """已是坐标时直接返回坐标（不依赖 API）。"""
        mock_http({"status": "1", "geocodes": [{"location": "116.0,40.0"}]})
        assert geocode.geocode_or_raw("116.0,40.0") == "116.0,40.0"

    def test_geocode_many(self, mock_http):
        """批量地理编码。"""
        mock_http(
            {
                "status": "1",
                "geocodes": [{"location": "116.39,39.90"}],
            }
        )
        resolved, failed = geocode.geocode_many(["故宫", "颐和园"], city="北京")
        assert resolved == ["116.39,39.90", "116.39,39.90"]
        assert failed == []
