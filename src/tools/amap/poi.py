from typing import Dict, Any, Optional, List

from src.config.settings import get_settings
from src.utils.http import cached_json_get
from src.utils.logger import logger

# 高德 POI 类型编码
TYPE_SCENIC = "110000"   # 风景名胜
TYPE_FOOD = "050000"     # 餐饮服务
TYPE_HOTEL = "100000"    # 住宿服务

# 预算级别 -> 价格区间（单位：元）。cost 缺失的酒店条目在过滤时保留（避免误删无价目数据）。
BUDGET_RANGES = {
    "经济型": (None, 300),
    "经济": (None, 300),
    "舒适型": (300, 600),
    "舒适": (300, 600),
    "高档型": (600, 1000),
    "高档": (600, 1000),
    "豪华型": (1000, None),
    "豪华": (1000, None),
}

# 预算级别 -> 关键词（用于向高德发起更贴合档位的搜索，随后再按价格精确过滤）
BUDGET_KEYWORDS = {
    "经济型": "经济型酒店 快捷酒店 青年旅舍",
    "经济": "经济型酒店 快捷酒店 青年旅舍",
    "舒适型": "舒适型酒店 商务酒店 三星酒店",
    "舒适": "舒适型酒店 商务酒店 三星酒店",
    "高档型": "高档酒店 四星级酒店",
    "高档": "高档酒店 四星级酒店",
    "豪华型": "豪华酒店 五星级酒店 度假酒店",
    "豪华": "豪华酒店 五星级酒店 度假酒店",
}


def _parse_cost(value: Any) -> Optional[float]:
    """健壮地解析 ``biz_ext.cost`` 为浮点数；缺失 / 非数字返回 None。"""
    if value is None:
        return None
    try:
        cost = float(value)
    except (TypeError, ValueError):
        return None
    return cost


def _in_budget(cost: Optional[float], low: Optional[float], high: Optional[float]) -> bool:
    """判断价格是否落在 ``[low, high)`` 区间（low/high 可为 None 表示开区间）。"""
    if cost is None:
        return False
    if low is not None and cost < low:
        return False
    if high is not None and cost >= high:
        return False
    return True


class POITool:
    BASE_URL = "https://restapi.amap.com/v5/place/text"

    @classmethod
    def search_poi(
        cls,
        keywords: str,
        city: Optional[str] = None,
        types: Optional[str] = None,
        page_size: int = 10,
        with_business: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """搜索 POI。

        Args:
            keywords: 关键词。
            city: 城市名 / adcode，限定搜索范围。
            types: POI 类型编码。
            page_size: 每页数量。
            with_business: 是否请求附加业务字段（``biz_ext``，含评分 / 人均价）。
                高德 V5 默认不返回 ``biz_ext``，需要显式通过 ``show_fields`` 申请；
                酒店 / 美食展示评分价格时应置 True。
        """
        params = {
            "key": get_settings().AMAP_API_KEY,
            "keywords": keywords,
            "page_size": page_size,
        }

        if city:
            params["city"] = city
        if types:
            params["types"] = types
        if with_business:
            # V5 接口：show_fields=biz_ext 才会返回评分 / 人均消费等业务字段
            params["show_fields"] = "biz_ext"

        cache_key = (
            f"poi:{keywords}:{city or ''}:{types or ''}:{page_size}:{with_business}"
        )
        data = cached_json_get(cls.BASE_URL, params, cache_key=cache_key)
        if data and data.get("status") == "1":
            return data
        if data:
            logger.error("高德POI搜索API错误: %s", data.get("info", "未知错误"))
        return None

    @classmethod
    def search_scenic_spots(cls, city: str, page_size: int = 10) -> Optional[Dict[str, Any]]:
        return cls.search_poi(keywords="景点", city=city, types=TYPE_SCENIC, page_size=page_size)

    @classmethod
    def search_food(cls, city: str, page_size: int = 10) -> Optional[Dict[str, Any]]:
        # 美食展示评分 / 人均，启用业务字段
        return cls.search_poi(
            keywords="美食", city=city, types=TYPE_FOOD, page_size=page_size, with_business=True
        )

    @classmethod
    def search_hotel(cls, city: str, page_size: int = 10) -> Optional[Dict[str, Any]]:
        # 酒店展示评分 / 参考价，启用业务字段
        return cls.search_poi(
            keywords="酒店", city=city, types=TYPE_HOTEL, page_size=page_size, with_business=True
        )

    @classmethod
    def search_hotel_by_budget(
        cls, city: str, budget: str = "", page_size: int = 10
    ) -> Optional[Dict[str, Any]]:
        """根据预算搜索酒店。

        budget 可以是 '经济型'(<300), '舒适型'(300-600), '高档型'(600-1000), '豪华型'(>1000)。
        搜索先按关键词缩小范围，再按 ``biz_ext.cost`` 精确过滤价格；
        ``cost`` 缺失的条目保留（避免误删无价目数据的酒店）。
        """
        budget_lower = budget.strip().lower() if budget else ""
        keywords = BUDGET_KEYWORDS.get(budget_lower, "酒店")
        data = cls.search_poi(
            keywords=keywords,
            city=city,
            types=TYPE_HOTEL,
            page_size=page_size,
            with_business=True,
        )
        if not data or "pois" not in data:
            return data

        # 未知预算级别：不按价格过滤，仅按关键词搜索（原行为）
        if budget_lower not in BUDGET_RANGES:
            return data

        low, high = BUDGET_RANGES[budget_lower]
        pois = data["pois"]
        filtered: List[Dict[str, Any]] = []
        no_cost: List[Dict[str, Any]] = []
        for poi in pois:
            biz_ext = poi.get("biz_ext", {})
            cost = _parse_cost(biz_ext.get("cost")) if isinstance(biz_ext, dict) else None
            if cost is None:
                no_cost.append(poi)
            elif _in_budget(cost, low, high):
                filtered.append(poi)

        # 命中区间的优先，cost 缺失的兜底保留
        data["pois"] = filtered + no_cost
        return data

    @classmethod
    def format_hotel_with_budget(cls, poi_data: Dict[str, Any], budget: str = "") -> str:
        """格式化酒店列表，标注预算级别"""
        if not poi_data or "pois" not in poi_data:
            return "暂无符合条件的住宿信息"

        pois = poi_data["pois"]
        budget_label = f"({budget})" if budget else ""
        lines = [f"\n🏨 推荐住宿{budget_label}："]

        for idx, poi in enumerate(pois[:10], 1):
            name = poi.get("name", "未知")
            address = poi.get("address", "地址未知")
            biz_ext = poi.get("biz_ext", {})
            rating = biz_ext.get("rating", "") if isinstance(biz_ext, dict) else ""
            cost = biz_ext.get("cost", "") if isinstance(biz_ext, dict) else ""
            lines.append(f"{idx}. {name}")
            lines.append(f"   地址：{address}")
            if rating:
                lines.append(f"   评分：{rating}")
            if cost:
                lines.append(f"   参考价格：{cost}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def format_poi_list(cls, poi_data: Dict[str, Any], title: str = "搜索结果") -> str:
        if not poi_data or "pois" not in poi_data:
            return f"暂无{title}信息"

        pois = poi_data["pois"]
        result = [f"\n📍 {title}："]

        for idx, poi in enumerate(pois[:10], 1):
            name = poi.get("name", "未知")
            address = poi.get("address", "地址未知")
            location = poi.get("location", "")
            result.append(f"{idx}. {name}")
            result.append(f"   地址：{address}")
            if location:
                result.append(f"   坐标：{location}")
            result.append("")

        return "\n".join(result)
