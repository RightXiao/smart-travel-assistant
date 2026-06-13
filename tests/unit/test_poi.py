import pytest
from unittest.mock import Mock, patch
from src.tools.amap.poi import POITool


class TestPOITool:
    """POI工具单元测试。"""

    @patch("src.tools.amap.poi.requests.get")
    def test_search_poi_success(self, mock_get):
        """测试成功搜索POI。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "pois": [
                {
                    "name": "故宫博物院",
                    "address": "景山前街4号",
                    "location": "116.397428,39.90923",
                }
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = POITool.search_poi("景点", city="北京")
        assert result is not None
        assert "pois" in result
        assert len(result["pois"]) > 0

    @patch("src.tools.amap.poi.requests.get")
    def test_search_poi_failure(self, mock_get):
        """测试搜索POI失败。"""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "0", "info": "错误"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = POITool.search_poi("景点", city="北京")
        assert result is None

    @patch("src.tools.amap.poi.requests.get")
    def test_search_scenic_spots_success(self, mock_get):
        """测试成功搜索景点。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "pois": [
                {
                    "name": "故宫博物院",
                    "address": "景山前街4号",
                    "location": "116.397428,39.90923",
                }
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = POITool.search_scenic_spots("北京")
        assert result is not None
        assert "pois" in result

    @patch("src.tools.amap.poi.requests.get")
    def test_search_food_success(self, mock_get):
        """测试成功搜索美食。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "pois": [
                {
                    "name": "全聚德烤鸭",
                    "address": "前门大街30号",
                    "location": "116.397428,39.90923",
                }
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = POITool.search_food("北京")
        assert result is not None
        assert "pois" in result

    @patch("src.tools.amap.poi.requests.get")
    def test_search_hotel_success(self, mock_get):
        """测试成功搜索酒店。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "pois": [
                {
                    "name": "北京饭店",
                    "address": "东长安街33号",
                    "location": "116.397428,39.90923",
                }
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = POITool.search_hotel("北京")
        assert result is not None
        assert "pois" in result

    def test_format_poi_list_success(self):
        """测试格式化POI列表。"""
        poi_data = {
            "pois": [
                {
                    "name": "故宫博物院",
                    "address": "景山前街4号",
                    "location": "116.397428,39.90923",
                },
                {
                    "name": "天坛公园",
                    "address": "天坛路甲1号",
                    "location": "116.407428,39.88223",
                },
            ]
        }
        result = POITool.format_poi_list(poi_data, "热门景点")
        assert "热门景点" in result
        assert "故宫博物院" in result
        assert "天坛公园" in result

    def test_format_poi_list_empty(self):
        """测试格式化空POI列表。"""
        result = POITool.format_poi_list({}, "热门景点")
        assert "暂无热门景点信息" in result

    @patch("src.tools.amap.poi.requests.get")
    def test_search_hotel_by_budget_economic(self, mock_get):
        """测试按经济型预算搜索酒店。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "pois": [
                {
                    "name": "如家酒店",
                    "address": "某路某号",
                    "location": "116.397428,39.90923",
                    "biz_ext": {"rating": "4.5", "cost": "200"},
                }
            ],
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = POITool.search_hotel_by_budget("北京", "经济型")
        assert result is not None
        assert "pois" in result

    def test_format_hotel_with_budget_success(self):
        """测试格式化带预算的酒店列表。"""
        poi_data = {
            "pois": [
                {
                    "name": "如家酒店",
                    "address": "某路某号",
                    "location": "116.397428,39.90923",
                    "biz_ext": {"rating": "4.5", "cost": "200"},
                }
            ]
        }
        result = POITool.format_hotel_with_budget(poi_data, "经济型")
        assert "经济型" in result
        assert "如家酒店" in result
        assert "200" in result
