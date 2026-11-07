"""高德地图工具层 — 以 ``StructuredTool`` 暴露给 Agent。

从旧版「``Tool`` + ``"|"`` 分隔符字符串协议」升级为**结构化参数**：每个工具
声明 pydantic ``args_schema``，LLM 通过原生 function calling 直接传 JSON 字段
（city / origin / destination / spots 各自独立），消除分隔符歧义——景点名、
城市名中含逗号 / 竖线等不再破坏解析。

- 工具名保持中文不变（与 SystemPrompt 及既有对话习惯一致）；
- 所有工具输出在返回给 LLM 前统一经 :func:`sanitize_tool_output` 清洗，
  降低提示注入与密钥泄漏风险；
- 路线类工具把「地名无法定位」转成可读提示，LLM 可据此引导用户修正输入。
"""
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.tools.amap.poi import POITool
from src.tools.amap.route import RouteResolutionError, RouteTool
from src.tools.amap.weather import WeatherTool
from src.utils.logger import logger
from src.utils.sanitize import sanitize_tool_output

# ---------------------------------------------------------------------------
# 参数 Schema（LLM 通过 function calling 传结构化字段）
# ---------------------------------------------------------------------------


class CityInput(BaseModel):
    city: str = Field(description="城市名称，如：北京、上海")


class HotelBudgetInput(BaseModel):
    city: str = Field(description="城市名称，如：北京")
    budget: str = Field(
        default="",
        description="预算级别：经济型/舒适型/高档型/豪华型；留空表示不限预算",
    )


class DrivingRouteInput(BaseModel):
    origin: str = Field(description="起点：地名或「经度,纬度」坐标，如：天安门")
    destination: str = Field(description="终点：地名或「经度,纬度」坐标，如：故宫博物院")
    city: Optional[str] = Field(default=None, description="所在城市（可选），用于提升地名定位准确性")


class TransitRouteInput(BaseModel):
    origin: str = Field(description="起点：地名或「经度,纬度」坐标")
    destination: str = Field(description="终点：地名或「经度,纬度」坐标")
    city: str = Field(description="所在城市（公交路线必填），如：北京")


class MultiSpotRouteInput(BaseModel):
    city: str = Field(description="景点所在城市，如：北京")
    spots: list[str] = Field(min_length=2, description="景点名称列表（至少 2 个），按希望游览的顺序给出")
    optimize_order: bool = Field(
        default=False,
        description="是否按地理位置就近重排景点顺序以减少绕路（会改变游览顺序）",
    )


# ---------------------------------------------------------------------------
# 工具实现（入参即结构化字段；输出统一清洗）
# ---------------------------------------------------------------------------


def _weather_func(city: str) -> str:
    try:
        data = WeatherTool.get_weather(city)
        if data:
            return sanitize_tool_output(WeatherTool.format_weather_info(data))
        return "抱歉，暂时无法获取天气信息"
    except Exception as e:
        logger.error("实时天气查询失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取天气信息"


def _forecast_func(city: str) -> str:
    try:
        data = WeatherTool.get_weather_forecast(city)
        if data:
            return sanitize_tool_output(WeatherTool.format_forecast_info(data))
        return "抱歉，暂时无法获取天气预报信息"
    except Exception as e:
        logger.error("天气预报查询失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取天气预报信息"


def _scenic_spots_func(city: str) -> str:
    try:
        data = POITool.search_scenic_spots(city)
        if data:
            return sanitize_tool_output(POITool.format_poi_list(data, title="热门景点"))
        return "抱歉，暂时无法获取景点信息"
    except Exception as e:
        logger.error("景点查询失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取景点信息"


def _food_func(city: str) -> str:
    try:
        data = POITool.search_food(city)
        if data:
            return sanitize_tool_output(POITool.format_poi_list(data, title="当地美食"))
        return "抱歉，暂时无法获取美食信息"
    except Exception as e:
        logger.error("美食查询失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取美食信息"


def _hotel_func(city: str) -> str:
    try:
        data = POITool.search_hotel(city)
        if data:
            return sanitize_tool_output(POITool.format_poi_list(data, title="推荐住宿"))
        return "抱歉，暂时无法获取住宿信息"
    except Exception as e:
        logger.error("住宿查询失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取住宿信息"


def _hotel_budget_func(city: str, budget: str = "") -> str:
    try:
        data = POITool.search_hotel_by_budget(city, budget)
        if data:
            return sanitize_tool_output(POITool.format_hotel_with_budget(data, budget))
        return "抱歉，暂时无法获取住宿信息"
    except Exception as e:
        logger.error("按预算查询住宿失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取住宿信息，请检查预算级别是否为：经济型/舒适型/高档型/豪华型。"


def _driving_route_func(
    origin: str, destination: str, city: Optional[str] = None
) -> str:
    try:
        data = RouteTool.get_driving_route(origin, destination, city=city)
        if data:
            return sanitize_tool_output(RouteTool.format_driving_route(data))
        return "抱歉，暂时无法获取路线信息"
    except RouteResolutionError as e:
        # 定位失败原因明确可读，让 LLM 能据此提示用户修正输入
        logger.warning("驾车路线规划地名解析失败: %s", e)
        return str(e)
    except Exception as e:
        logger.error("驾车路线规划失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取驾车路线信息"


def _transit_route_func(origin: str, destination: str, city: str) -> str:
    try:
        data = RouteTool.get_transit_route(origin, destination, city)
        if data:
            return sanitize_tool_output(RouteTool.format_transit_route(data))
        return "抱歉，暂时无法获取公交路线信息"
    except RouteResolutionError as e:
        logger.warning("公交路线规划地名解析失败: %s", e)
        return str(e)
    except Exception as e:
        logger.error("公交路线规划失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取公交路线信息"


def _multi_spot_route_func(
    city: str, spots: list[str], optimize_order: bool = False
) -> str:
    try:
        data = RouteTool.plan_multi_spot_route(
            spots, city=city, optimize_order=optimize_order
        )
        if data:
            return sanitize_tool_output(RouteTool.format_multi_spot_route(data))
        return "抱歉，暂时无法规划多景点路线"
    except Exception as e:
        logger.error("多景点路线规划失败: %s", e, exc_info=True)
        return "抱歉，暂时无法规划多景点路线"


def _dressing_func(city: str) -> str:
    try:
        data = WeatherTool.get_weather(city)
        if not data:
            return "抱歉，暂时无法获取天气信息来提供穿搭建议"
        weather_info = WeatherTool.format_weather_info(data)
        advice = WeatherTool.get_dressing_advice(data)
        return sanitize_tool_output(f"{weather_info}\n\n👗 穿搭建议：\n{advice}")
    except Exception as e:
        logger.error("穿搭建议查询失败: %s", e, exc_info=True)
        return "抱歉，暂时无法获取天气信息来提供穿搭建议"


def get_travel_tools() -> list:
    """构建全部旅行工具（每次调用返回新实例，工具为无状态封装）。"""
    return [
        StructuredTool.from_function(
            func=_weather_func,
            name="查询实时天气",
            description="查询指定城市的实时天气，输入城市名称（如：北京、上海）",
            args_schema=CityInput,
        ),
        StructuredTool.from_function(
            func=_forecast_func,
            name="查询天气预报",
            description="查询指定城市未来4天的天气预报，输入城市名称",
            args_schema=CityInput,
        ),
        StructuredTool.from_function(
            func=_scenic_spots_func,
            name="查询景点",
            description="查询指定城市的热门景点，输入城市名称（如：北京、上海）",
            args_schema=CityInput,
        ),
        StructuredTool.from_function(
            func=_food_func,
            name="查询美食",
            description="查询指定城市的当地美食推荐，输入城市名称",
            args_schema=CityInput,
        ),
        StructuredTool.from_function(
            func=_hotel_func,
            name="查询住宿",
            description="查询指定城市的酒店住宿信息，输入城市名称",
            args_schema=CityInput,
        ),
        StructuredTool.from_function(
            func=_hotel_budget_func,
            name="按预算查询住宿",
            description=(
                "根据预算查询城市住宿。预算级别可选："
                "经济型(300元以下)、舒适型(300-600元)、高档型(600-1000元)、豪华型(1000元以上)"
            ),
            args_schema=HotelBudgetInput,
        ),
        StructuredTool.from_function(
            func=_driving_route_func,
            name="驾车路线规划",
            description=("查询两点之间的驾车路线。输入地名即可（自动地理编码定位），" "可选附所在城市提升定位准确性"),
            args_schema=DrivingRouteInput,
        ),
        StructuredTool.from_function(
            func=_transit_route_func,
            name="公交路线规划",
            description="查询两点之间的公交/地铁路线，需提供所在城市。输入地名即可（自动定位）",
            args_schema=TransitRouteInput,
        ),
        StructuredTool.from_function(
            func=_multi_spot_route_func,
            name="多景点路线规划",
            description=("规划多个景点之间的游览路线（如：北京的天安门、故宫、颐和园）。" "可选择按地理位置就近优化游览顺序"),
            args_schema=MultiSpotRouteInput,
        ),
        StructuredTool.from_function(
            func=_dressing_func,
            name="查询穿搭建议",
            description="根据指定城市的实时天气，提供穿搭建议，输入城市名称",
            args_schema=CityInput,
        ),
    ]
