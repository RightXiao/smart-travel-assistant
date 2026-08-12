"""高德地理编码工具：地名 -> 经纬度坐标。

ReAct 工具在向用户暴露 ``驾车路线规划`` / ``公交路线规划`` / ``多景点路线规划`` 时，
输入是自然语言地名（如 ``故宫``）。但高德 ``direction/*`` 路线规划接口要求
``origin`` / ``destination`` 必须是 ``经度,纬度`` 坐标，直接传地名会返回 ``INVALID_USER_KEY`` 之外的
参数错误，导致路线规划静默失败。

本模块统一封装 ``地名 -> location`` 的转换，并做进程内缓存，避免重复请求。
"""
from __future__ import annotations

from typing import Optional, Tuple

from src.config.settings import get_settings
from src.utils.http import cached_json_get
from src.utils.logger import logger

BASE_URL = "https://restapi.amap.com/v3/geocode/geo"


def geocode(address: str, city: Optional[str] = None) -> Optional[str]:
    """将地名转为 ``经度,纬度`` 字符串。

    Args:
        address: 地名，如 ``故宫博物院``。
        city: 指定城市以提升准确性，如 ``北京``。

    Returns:
        形如 ``"116.397428,39.90923"`` 的坐标；失败返回 None。
    """
    if not address or not address.strip():
        return None

    params = {
        "key": get_settings().AMAP_API_KEY,
        "address": address.strip(),
    }
    if city:
        params["city"] = city

    cache_key = f"geocode:{address.strip()}:{city or ''}"
    data = cached_json_get(BASE_URL, params, cache_key=cache_key)
    if not data:
        return None

    if data.get("status") != "1":
        logger.error("高德地理编码失败 (%s): %s", address, data.get("info", "未知错误"))
        return None

    geocodes = data.get("geocodes") or []
    if not geocodes:
        logger.warning("地理编码无结果: %s", address)
        return None

    location = geocodes[0].get("location", "")
    return location or None


def geocode_or_raw(text: str, city: Optional[str] = None) -> str:
    """尝试地理编码；失败时原样返回（交由上层决定如何提示）。

    返回值保证非空字符串：要么是 ``经度,纬度``，要么是原始输入。
    """
    coord = geocode(text, city)
    return coord if coord else text.strip()


def geocode_many(
    places: list[str], city: Optional[str] = None
) -> Tuple[list[str], list[str]]:
    """批量地理编码。

    Returns:
        ``(resolved, failed)`` —— 成功转换为坐标的列表（保持原序），
        与未能解析的地名列表。
    """
    resolved: list[str] = []
    failed: list[str] = []
    for place in places:
        coord = geocode(place, city)
        if coord:
            resolved.append(coord)
        else:
            failed.append(place)
    return resolved, failed
