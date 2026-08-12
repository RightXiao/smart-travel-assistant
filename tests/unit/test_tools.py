from unittest.mock import patch

from src.tools import _normalize_separator, get_travel_tools


def _tool_by_name(name):
    tools = get_travel_tools()
    return next(t for t in tools if t.name == name)


class TestNormalizeSeparator:
    def test_normalizes_chinese_separators(self):
        assert _normalize_separator("北京，天安门、故宫；颐和园") == "北京|天安门|故宫|颐和园"

    def test_preserves_pipe(self):
        assert _normalize_separator("a|b|c") == "a|b|c"


class TestToolRegistry:
    def test_get_travel_tools_returns_list(self):
        tools = get_travel_tools()
        assert isinstance(tools, list)
        assert len(tools) == 10

    def test_expected_tool_names(self):
        names = [t.name for t in get_travel_tools()]
        for expected in [
            "查询实时天气",
            "查询天气预报",
            "查询景点",
            "查询美食",
            "查询住宿",
            "按预算查询住宿",
            "驾车路线规划",
            "公交路线规划",
            "多景点路线规划",
            "查询穿搭建议",
        ]:
            assert expected in names, f"缺少工具: {expected}"


class TestWeatherTools:
    def test_weather_tool_success(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = {
                "lives": [{"city": "北京", "weather": "晴", "temperature": "25"}]
            }
            result = _tool_by_name("查询实时天气").func("北京")
            assert "北京" in result

    def test_weather_tool_fallback(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = None
            result = _tool_by_name("查询实时天气").func("北京")
            assert "无法获取天气信息" in result


class TestPOITools:
    def test_scenic_spots_tool_success(self):
        with patch("src.tools.amap.poi.POITool.search_scenic_spots") as m:
            m.return_value = {"pois": [{"name": "故宫", "address": "x", "location": "y"}]}
            result = _tool_by_name("查询景点").func("北京")
            assert "故宫" in result

    def test_food_tool_fallback(self):
        with patch("src.tools.amap.poi.POITool.search_food") as m:
            m.return_value = None
            result = _tool_by_name("查询美食").func("北京")
            assert "无法获取美食信息" in result

    def test_hotel_budget_tool_parses(self):
        with patch("src.tools.amap.poi.POITool.search_hotel_by_budget") as m:
            m.return_value = {
                "pois": [{"name": "如家", "address": "x", "biz_ext": {"cost": "200"}}]
            }
            result = _tool_by_name("按预算查询住宿").func("北京,经济型")
            # 断言城市与预算被正确拆分
            args, _ = m.call_args
            assert args[0] == "北京"
            assert args[1] == "经济型"
            assert "如家" in result

    def test_hotel_budget_tool_error_sanitized(self):
        with patch("src.tools.amap.poi.POITool.search_hotel_by_budget") as m:
            m.side_effect = Exception("secret-api-key-abc123")
            result = _tool_by_name("按预算查询住宿").func("北京|经济型")
            # 异常信息不得泄漏给用户
            assert "secret-api-key" not in result
            assert "参数格式错误" in result


class TestRouteTools:
    def test_driving_route_tool_success(self):
        with patch("src.tools.amap.route.RouteTool.get_driving_route") as m:
            m.return_value = {
                "route": {
                    "paths": [{"duration": "600", "distance": "1000", "steps": []}]
                }
            }
            result = _tool_by_name("驾车路线规划").func("天安门|故宫")
            assert "驾车路线规划" in result

    def test_transit_route_requires_city(self):
        # 缺少城市时应返回明确提示，不再用 destination 冒充 city
        result = _tool_by_name("公交路线规划").func("天安门|故宫")
        assert "所在城市" in result

    def test_transit_route_success(self):
        with patch("src.tools.amap.route.RouteTool.get_transit_route") as m:
            m.return_value = {
                "route": {
                    "transits": [
                        {"duration": "600", "walking_distance": "100", "segments": []}
                    ]
                }
            }
            result = _tool_by_name("公交路线规划").func("天安门|故宫|北京")
            args, _ = m.call_args
            assert args[2] == "北京"
            assert "公交路线规划" in result

    def test_multi_spot_route_tool_success(self):
        with patch("src.tools.amap.route.RouteTool.plan_multi_spot_route") as m:
            m.return_value = {
                "segments": [
                    {"from": "天安门", "to": "故宫", "duration_minutes": 30, "distance_km": 5.0}
                ],
                "total_duration": 30,
                "total_distance": 5.0,
                "spot_count": 2,
                "mode": "driving",
            }
            result = _tool_by_name("多景点路线规划").func("北京|天安门|故宫")
            args, _ = m.call_args
            assert args[0] == ["天安门", "故宫"]
            assert "多景点路线规划" in result

    def test_multi_spot_route_insufficient_spots(self):
        result = _tool_by_name("多景点路线规划").func("北京|天安门")
        assert "至少需要" in result

    def test_driving_route_tool_error_sanitized(self):
        with patch("src.tools.amap.route.RouteTool.get_driving_route") as m:
            m.side_effect = Exception("internal-url-and-key")
            result = _tool_by_name("驾车路线规划").func("a|b")
            assert "internal-url-and-key" not in result
            assert "参数格式错误" in result


class TestDressingTool:
    def test_dressing_tool_success(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = {
                "lives": [{"temperature": "35", "weather": "晴", "windpower": "2"}]
            }
            result = _tool_by_name("查询穿搭建议").func("北京")
            assert "穿搭建议" in result
            assert "短袖" in result

    def test_dressing_tool_fallback(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = None
            result = _tool_by_name("查询穿搭建议").func("北京")
            assert "无法获取天气信息" in result
