"""地理计算公共函数：坐标解析与球面距离。

供路线模块（就近排序）与行程排程模块（逐日距离估算）共用。
"""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def parse_coord(text: str) -> tuple[float, float] | None:
    """把 ``"经度,纬度"`` 解析为 ``(lng, lat)`` 浮点对；失败返回 None。"""
    try:
        lng_s, lat_s = text.split(",", 1)
        return float(lng_s), float(lat_s)
    except (ValueError, AttributeError):
        return None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """两坐标点（经度, 纬度）间的大圆距离（公里）。"""
    lng1, lat1 = math.radians(a[0]), math.radians(a[1])
    lng2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlng, dlat = lng2 - lng1, lat2 - lat1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
