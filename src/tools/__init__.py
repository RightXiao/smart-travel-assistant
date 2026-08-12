from langchain_core.tools import Tool
from src.tools.amap.weather import WeatherTool
from src.tools.amap.poi import POITool
from src.tools.amap.route import RouteTool
from src.utils.logger import logger


def _normalize_separator(s: str) -> str:
    """把中文分隔符 / 多个分隔符统一成英文 ``|``，提升 LLM 输出鲁棒性。"""
    for ch in ("｜", "、", ",", "，", ";", "；"):
        s = s.replace(ch, "|")
    return s


def get_travel_tools():
    tools = []

    # --- 实时天气 ---
    def weather_tool_func(city: str) -> str:
        data = WeatherTool.get_weather(city)
        if data:
            return WeatherTool.format_weather_info(data)
        return "抱歉，暂时无法获取天气信息"

    tools.append(Tool(
        name="查询实时天气",
        func=weather_tool_func,
        description="查询指定城市的实时天气，输入参数为城市名称（如：北京、上海）",
    ))

    # --- 天气预报 ---
    def forecast_tool_func(city: str) -> str:
        data = WeatherTool.get_weather_forecast(city)
        if data:
            return WeatherTool.format_forecast_info(data)
        return "抱歉，暂时无法获取天气预报信息"

    tools.append(Tool(
        name="查询天气预报",
        func=forecast_tool_func,
        description="查询指定城市未来4天的天气预报，输入参数为城市名称",
    ))

    # --- 景点 ---
    def scenic_spots_tool_func(city: str) -> str:
        data = POITool.search_scenic_spots(city)
        if data:
            return POITool.format_poi_list(data, title="热门景点")
        return "抱歉，暂时无法获取景点信息"

    tools.append(Tool(
        name="查询景点",
        func=scenic_spots_tool_func,
        description="查询指定城市的热门景点，输入参数为城市名称（如：北京、上海）",
    ))

    # --- 美食 ---
    def food_tool_func(city: str) -> str:
        data = POITool.search_food(city)
        if data:
            return POITool.format_poi_list(data, title="当地美食")
        return "抱歉，暂时无法获取美食信息"

    tools.append(Tool(
        name="查询美食",
        func=food_tool_func,
        description="查询指定城市的当地美食推荐，输入参数为城市名称",
    ))

    # --- 住宿（基础） ---
    def hotel_tool_func(city: str) -> str:
        data = POITool.search_hotel(city)
        if data:
            return POITool.format_poi_list(data, title="推荐住宿")
        return "抱歉，暂时无法获取住宿信息"

    tools.append(Tool(
        name="查询住宿",
        func=hotel_tool_func,
        description="查询指定城市的酒店住宿信息，输入参数为城市名称",
    ))

    # --- 住宿（按预算） ---
    def hotel_budget_tool_func(input_str: str) -> str:
        try:
            normalized = _normalize_separator(input_str)
            parts = normalized.rsplit("|", 1)
            if len(parts) == 2:
                city = parts[0].strip()
                budget = parts[1].strip()
            else:
                city = parts[0].strip()
                budget = ""
            data = POITool.search_hotel_by_budget(city, budget)
            if data:
                return POITool.format_hotel_with_budget(data, budget)
            return "抱歉，暂时无法获取住宿信息"
        except Exception as e:
            logger.error("按预算查询住宿失败: %s", e, exc_info=True)
            return "参数格式错误，请使用格式：城市,预算级别（如：北京,经济型）。"

    tools.append(Tool(
        name="按预算查询住宿",
        func=hotel_budget_tool_func,
        description=(
            "根据预算查询城市住宿。输入格式：城市,预算级别。"
            "预算级别可选：经济型(300元以下)、舒适型(300-600元)、高档型(600-1000元)、豪华型(1000元以上)"
        ),
    ))

    # --- 驾车路线 ---
    def driving_route_tool_func(input_str: str) -> str:
        try:
            normalized = _normalize_separator(input_str)
            parts = [p.strip() for p in normalized.split("|")]
            if len(parts) < 2:
                return "参数格式错误，请使用格式：起点|终点（如：天安门|故宫博物院）。"
            origin = parts[0]
            destination = parts[1]
            # 第 3 段（可选）作为城市，提升地名定位准确性
            city = parts[2] if len(parts) >= 3 else None
            data = RouteTool.get_driving_route(origin, destination, city=city)
            if data:
                return RouteTool.format_driving_route(data)
            return "抱歉，暂时无法获取路线信息"
        except Exception as e:
            logger.error("驾车路线规划失败: %s", e, exc_info=True)
            return "参数格式错误，请使用格式：起点|终点（如：天安门|故宫博物院）。"

    tools.append(Tool(
        name="驾车路线规划",
        func=driving_route_tool_func,
        description="查询两点之间的驾车路线，输入格式：起点|终点（如：天安门|故宫博物院），也可附带所在城市：起点|终点|城市。输入地名即可，会自动定位",
    ))

    # --- 公交路线 ---
    def transit_route_tool_func(input_str: str) -> str:
        try:
            normalized = _normalize_separator(input_str)
            parts = [p.strip() for p in normalized.split("|")]
            if len(parts) < 2:
                return "参数格式错误，请使用格式：起点|终点|所在城市。"
            origin, destination = parts[0], parts[1]
            if len(parts) < 3:
                return "参数格式错误，请提供所在城市：起点|终点|所在城市。"
            city = parts[2]
            data = RouteTool.get_transit_route(origin, destination, city)
            if data:
                return RouteTool.format_transit_route(data)
            return "抱歉，暂时无法获取公交路线信息"
        except Exception as e:
            logger.error("公交路线规划失败: %s", e, exc_info=True)
            return "参数格式错误，请使用格式：起点|终点|所在城市。"

    tools.append(Tool(
        name="公交路线规划",
        func=transit_route_tool_func,
        description="查询两点之间的公交/地铁路线，输入格式：起点|终点|所在城市。输入地名即可，会自动定位",
    ))

    # --- 多景点路线 ---
    def multi_spot_route_tool_func(input_str: str) -> str:
        try:
            normalized = _normalize_separator(input_str)
            parts = [p.strip() for p in normalized.split("|") if p.strip()]
            if len(parts) < 3:
                return "至少需要 城市和2个景点 才能规划路线，格式：城市|景点1|景点2|景点3|..."
            city = parts[0]
            spots = parts[1:]
            data = RouteTool.plan_multi_spot_route(spots, city=city)
            if data:
                return RouteTool.format_multi_spot_route(data)
            return "抱歉，暂时无法规划多景点路线"
        except Exception as e:
            logger.error("多景点路线规划失败: %s", e, exc_info=True)
            return "参数格式错误，请使用格式：城市|景点1|景点2|景点3。"

    tools.append(Tool(
        name="多景点路线规划",
        func=multi_spot_route_tool_func,
        description=(
            "规划多个景点之间的最优游览路线。输入格式：城市|景点1|景点2|景点3|... "
            "（如：北京|天安门|故宫|颐和园|长城）"
        ),
    ))

    # --- 穿搭建议 ---
    def dressing_tool_func(city: str) -> str:
        """根据天气给出穿搭建议"""
        data = WeatherTool.get_weather(city)
        if not data:
            return "抱歉，暂时无法获取天气信息来提供穿搭建议"
        weather_info = WeatherTool.format_weather_info(data)
        advice = WeatherTool.get_dressing_advice(data)
        return f"{weather_info}\n\n👗 穿搭建议：\n{advice}"

    tools.append(Tool(
        name="查询穿搭建议",
        func=dressing_tool_func,
        description="根据指定城市的实时天气，提供穿搭建议，输入参数为城市名称",
    ))

    return tools
