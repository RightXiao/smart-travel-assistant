"""工具层测试（StructuredTool 结构化参数契约）。

LLM 通过 function calling 传 pydantic ``args_schema`` 字段；这里直接以
关键字参数调用底层 ``func`` 验证行为，并用 ``tool.invoke`` 验证 schema 约束。
"""
from unittest.mock import patch

import pytest
from langchain_core.tools import StructuredTool

from src.tools import get_travel_tools


def _tool_by_name(name):
    tools = get_travel_tools()
    return next(t for t in tools if t.name == name)


class TestToolRegistry:
    def test_get_travel_tools_returns_list(self):
        tools = get_travel_tools()
        assert isinstance(tools, list)
        assert len(tools) == 10

    def test_all_tools_are_structured(self):
        """所有工具应为 StructuredTool（结构化参数契约）。"""
        for tool in get_travel_tools():
            assert isinstance(tool, StructuredTool)
            assert tool.args_schema is not None

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
            result = _tool_by_name("查询实时天气").func(city="北京")
            assert "北京" in result

    def test_weather_tool_fallback(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = None
            result = _tool_by_name("查询实时天气").func(city="北京")
            assert "无法获取天气信息" in result

    def test_tool_output_sanitized(self):
        """工具输出中的疑似密钥应被脱敏后再进入 LLM 上下文。"""
        with patch(
            "src.tools.amap.weather.WeatherTool.get_weather"
        ) as m_weather, patch(
            "src.tools.amap.weather.WeatherTool.format_weather_info"
        ) as m_fmt:
            m_weather.return_value = {"lives": [{"city": "北京"}]}
            m_fmt.return_value = "天气晴 key=0123456789abcdef0123456789abcdef"
            result = _tool_by_name("查询实时天气").func(city="北京")
            assert "0123456789abcdef" not in result
            assert "[REDACTED]" in result

    def test_tool_exception_sanitized(self):
        """工具内部异常信息不得泄漏给 LLM / 用户。"""
        with patch(
            "src.tools.amap.weather.WeatherTool.get_weather",
            side_effect=Exception("internal-url-with-secret-key"),
        ):
            result = _tool_by_name("查询实时天气").func(city="北京")
            assert "internal-url-with-secret-key" not in result


class TestPOITools:
    def test_scenic_spots_tool_success(self):
        with patch("src.tools.amap.poi.POITool.search_scenic_spots") as m:
            m.return_value = {"pois": [{"name": "故宫", "address": "x", "location": "y"}]}
            result = _tool_by_name("查询景点").func(city="北京")
            assert "故宫" in result

    def test_food_tool_fallback(self):
        with patch("src.tools.amap.poi.POITool.search_food") as m:
            m.return_value = None
            result = _tool_by_name("查询美食").func(city="北京")
            assert "无法获取美食信息" in result

    def test_hotel_budget_tool_structured_args(self):
        """城市与预算作为独立结构化字段传入（不再有分隔符解析）。"""
        with patch("src.tools.amap.poi.POITool.search_hotel_by_budget") as m:
            m.return_value = {
                "pois": [{"name": "如家", "address": "x", "biz_ext": {"cost": "200"}}]
            }
            result = _tool_by_name("按预算查询住宿").func(city="北京", budget="经济型")
            args, kwargs = m.call_args
            assert args[0] == "北京"
            assert args[1] == "经济型"
            assert "如家" in result

    def test_hotel_budget_tool_error_sanitized(self):
        with patch("src.tools.amap.poi.POITool.search_hotel_by_budget") as m:
            m.side_effect = Exception("secret-api-key-abc123")
            result = _tool_by_name("按预算查询住宿").func(city="北京", budget="经济型")
            # 异常信息不得泄漏给用户
            assert "secret-api-key" not in result
            assert "无法获取住宿信息" in result


class TestRouteTools:
    def test_driving_route_tool_success(self):
        with patch("src.tools.amap.route.RouteTool.get_driving_route") as m:
            m.return_value = {
                "route": {
                    "paths": [{"duration": "600", "distance": "1000", "steps": []}]
                }
            }
            result = _tool_by_name("驾车路线规划").func(origin="天安门", destination="故宫")
            assert "驾车路线规划" in result

    def test_driving_route_unresolvable_place(self):
        from src.tools.amap.route import RouteResolutionError

        with patch(
            "src.tools.amap.route.RouteTool.get_driving_route",
            side_effect=RouteResolutionError("无法定位起点：「不存在」"),
        ):
            result = _tool_by_name("驾车路线规划").func(origin="不存在", destination="故宫")
            assert "无法定位起点" in result

    def test_transit_route_requires_city_in_schema(self):
        """公交路线的 city 为必填字段（由 args_schema 约束，替代旧字符串校验）。"""
        with pytest.raises(Exception):
            _tool_by_name("公交路线规划").invoke({"origin": "天安门", "destination": "故宫"})

    def test_transit_route_success(self):
        with patch("src.tools.amap.route.RouteTool.get_transit_route") as m:
            m.return_value = {
                "route": {
                    "transits": [
                        {"duration": "600", "walking_distance": "100", "segments": []}
                    ]
                }
            }
            result = _tool_by_name("公交路线规划").func(
                origin="天安门", destination="故宫", city="北京"
            )
            args, _ = m.call_args
            assert args[2] == "北京"
            assert "公交路线规划" in result

    def test_multi_spot_route_tool_structured_args(self):
        """spots 以真正的列表传入（不再拆分隔符）。"""
        with patch("src.tools.amap.route.RouteTool.plan_multi_spot_route") as m:
            m.return_value = {
                "segments": [
                    {
                        "from": "天安门",
                        "to": "故宫",
                        "duration_minutes": 30,
                        "distance_km": 5.0,
                    }
                ],
                "total_duration": 30,
                "total_distance": 5.0,
                "spot_count": 2,
                "mode": "driving",
            }
            result = _tool_by_name("多景点路线规划").func(city="北京", spots=["天安门", "故宫"])
            args, kwargs = m.call_args
            assert args[0] == ["天安门", "故宫"]
            assert kwargs.get("optimize_order") is False
            assert "多景点路线规划" in result

    def test_multi_spot_route_optimize_order_passed(self):
        with patch("src.tools.amap.route.RouteTool.plan_multi_spot_route") as m:
            m.return_value = {"segments": [], "mode": "driving"}
            _tool_by_name("多景点路线规划").func(
                city="北京", spots=["天安门", "故宫", "颐和园"], optimize_order=True
            )
            assert m.call_args.kwargs.get("optimize_order") is True

    def test_multi_spot_route_insufficient_spots(self):
        result = _tool_by_name("多景点路线规划").func(city="北京", spots=["天安门"])
        assert "至少需要" in result

    def test_multi_spot_requires_two_spots_in_schema(self):
        with pytest.raises(Exception):
            _tool_by_name("多景点路线规划").invoke({"city": "北京", "spots": ["故宫"]})


class TestDressingTool:
    def test_dressing_tool_success(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = {
                "lives": [{"temperature": "35", "weather": "晴", "windpower": "2"}]
            }
            result = _tool_by_name("查询穿搭建议").func(city="北京")
            assert "穿搭建议" in result
            assert "短袖" in result

    def test_dressing_tool_fallback(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m:
            m.return_value = None
            result = _tool_by_name("查询穿搭建议").func(city="北京")
            assert "无法获取天气信息" in result
