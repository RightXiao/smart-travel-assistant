from unittest.mock import patch

from src.tools.amap.poi import POITool


class TestPOITool:
    """POI 工具单元测试。"""

    def test_search_poi_success(self, mock_http):
        """测试成功搜索 POI。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {
                        "name": "故宫博物院",
                        "address": "景山前街4号",
                        "location": "116.397428,39.90923",
                    }
                ],
            }
        )
        result = POITool.search_poi("景点", city="北京")
        assert result is not None
        assert "pois" in result
        assert len(result["pois"]) > 0

    def test_search_poi_failure(self, mock_http):
        """测试搜索 POI 失败。"""
        mock_http({"status": "0", "info": "错误"})
        result = POITool.search_poi("景点", city="北京")
        assert result is None

    def test_search_scenic_spots_success(self, mock_http):
        """测试成功搜索景点。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {
                        "name": "故宫博物院",
                        "address": "景山前街4号",
                        "location": "116.397428,39.90923",
                    }
                ],
            }
        )
        result = POITool.search_scenic_spots("北京")
        assert result is not None
        assert "pois" in result

    def test_search_food_requests_business_fields(self, mock_http):
        """测试美食搜索会请求业务字段（评分/人均）。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {
                        "name": "全聚德烤鸭",
                        "address": "前门大街30号",
                        "location": "116.397428,39.90923",
                    }
                ],
            }
        )
        with patch("src.tools.amap.poi.cached_json_get") as mock_get:
            mock_get.return_value = {"status": "1", "pois": []}
            POITool.search_food("北京")
            args, _ = mock_get.call_args
            # cached_json_get(url, params, cache_key=...) -> params 是第 2 个位置参数
            # 关键修复点：美食搜索必须显式带 show_fields
            assert args[1].get("show_fields") == "biz_ext"

    def test_search_hotel_requests_business_fields(self, mock_http):
        """测试酒店搜索会请求业务字段（评分/参考价）—— 核心修复点。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {
                        "name": "北京饭店",
                        "address": "东长安街33号",
                        "location": "116.397428,39.90923",
                    }
                ],
            }
        )
        with patch("src.tools.amap.poi.cached_json_get") as mock_get:
            mock_get.return_value = {"status": "1", "pois": []}
            POITool.search_hotel("北京")
            args, _ = mock_get.call_args
            assert args[1].get("show_fields") == "biz_ext"

    def test_format_poi_list_success(self):
        """测试格式化 POI 列表。"""
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
        """测试格式化空 POI 列表。"""
        result = POITool.format_poi_list({}, "热门景点")
        assert "暂无热门景点信息" in result

    def test_search_hotel_by_budget_economic(self, mock_http):
        """测试按经济型预算搜索酒店。"""
        mock_http(
            {
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
        )
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

    def test_search_hotel_by_budget_filters_by_price(self, mock_http):
        """预算搜索应按 biz_ext.cost 过滤价格（核心修复点）。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {"name": "经济酒店", "biz_ext": {"cost": "150"}},
                    {"name": "豪华酒店", "biz_ext": {"cost": "1200"}},
                    {"name": "无价目酒店", "biz_ext": {}},
                ],
            }
        )
        result = POITool.search_hotel_by_budget("北京", "经济型")
        names = [p["name"] for p in result["pois"]]
        # 150 元命中经济型(<300)；1200 元被过滤；无价目兜底保留
        assert "经济酒店" in names
        assert "豪华酒店" not in names
        assert "无价目酒店" in names

    def test_search_hotel_by_budget_high_end(self, mock_http):
        """高档/豪华区间过滤边界。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {"name": "普通", "biz_ext": {"cost": "500"}},
                    {"name": "五星", "biz_ext": {"cost": "1500"}},
                ],
            }
        )
        result = POITool.search_hotel_by_budget("北京", "豪华型")
        names = [p["name"] for p in result["pois"]]
        assert "五星" in names
        assert "普通" not in names

    def test_search_hotel_by_budget_unknown_level_no_filter(self, mock_http):
        """未知预算级别不按价格过滤（仅关键词搜索）。"""
        mock_http(
            {
                "status": "1",
                "pois": [
                    {"name": "任意酒店", "biz_ext": {"cost": "800"}},
                ],
            }
        )
        result = POITool.search_hotel_by_budget("北京", "随便")
        assert [p["name"] for p in result["pois"]] == ["任意酒店"]

    def test_parse_cost_robust(self):
        """_parse_cost 对非法/缺失值应返回 None 或浮点。"""
        from src.tools.amap.poi import _parse_cost
        assert _parse_cost("200") == 200.0
        assert _parse_cost(300) == 300.0
        assert _parse_cost("abc") is None
        assert _parse_cost(None) is None
        assert _parse_cost("") is None
