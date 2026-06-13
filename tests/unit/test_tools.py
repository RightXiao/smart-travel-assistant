import pytest
from src.tools import get_travel_tools


class TestTools:
    """工具集成测试。"""

    def test_get_travel_tools_returns_list(self):
        """测试获取旅行工具返回列表。"""
        tools = get_travel_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_get_travel_tools_contains_expected_tools(self):
        """测试旅行工具包含预期的工具。"""
        tools = get_travel_tools()
        tool_names = [tool.name for tool in tools]

        expected_tools = [
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
        ]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"缺少工具: {expected_tool}"

    def test_weather_tool_func(self):
        """测试天气工具函数。"""
        tools = get_travel_tools()
        weather_tool = next(
            tool for tool in tools if tool.name == "查询实时天气"
        )
        # 由于没有实际的API密钥，这里只测试函数存在
        assert callable(weather_tool.func)

    def test_forecast_tool_func(self):
        """测试天气预报工具函数。"""
        tools = get_travel_tools()
        forecast_tool = next(
            tool for tool in tools if tool.name == "查询天气预报"
        )
        assert callable(forecast_tool.func)

    def test_scenic_spots_tool_func(self):
        """测试景点工具函数。"""
        tools = get_travel_tools()
        spots_tool = next(
            tool for tool in tools if tool.name == "查询景点"
        )
        assert callable(spots_tool.func)

    def test_food_tool_func(self):
        """测试美食工具函数。"""
        tools = get_travel_tools()
        food_tool = next(
            tool for tool in tools if tool.name == "查询美食"
        )
        assert callable(food_tool.func)

    def test_hotel_tool_func(self):
        """测试住宿工具函数。"""
        tools = get_travel_tools()
        hotel_tool = next(
            tool for tool in tools if tool.name == "查询住宿"
        )
        assert callable(hotel_tool.func)

    def test_hotel_budget_tool_func(self):
        """测试按预算查询住宿工具函数。"""
        tools = get_travel_tools()
        hotel_budget_tool = next(
            tool for tool in tools if tool.name == "按预算查询住宿"
        )
        assert callable(hotel_budget_tool.func)

    def test_driving_route_tool_func(self):
        """测试驾车路线工具函数。"""
        tools = get_travel_tools()
        driving_tool = next(
            tool for tool in tools if tool.name == "驾车路线规划"
        )
        assert callable(driving_tool.func)

    def test_transit_route_tool_func(self):
        """测试公交路线工具函数。"""
        tools = get_travel_tools()
        transit_tool = next(
            tool for tool in tools if tool.name == "公交路线规划"
        )
        assert callable(transit_tool.func)

    def test_multi_spot_route_tool_func(self):
        """测试多景点路线工具函数。"""
        tools = get_travel_tools()
        multi_spot_tool = next(
            tool for tool in tools if tool.name == "多景点路线规划"
        )
        assert callable(multi_spot_tool.func)

    def test_dressing_tool_func(self):
        """测试穿搭建议工具函数。"""
        tools = get_travel_tools()
        dressing_tool = next(
            tool for tool in tools if tool.name == "查询穿搭建议"
        )
        assert callable(dressing_tool.func)
