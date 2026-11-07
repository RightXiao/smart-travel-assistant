import re
from typing import Any, Optional

from src.config.settings import get_settings
from src.tools.amap import geocode
from src.tools.amap.geo import haversine_km, parse_coord
from src.utils.http import acached_json_get, cached_json_get
from src.utils.logger import logger


def _strip_tags(text: Any) -> str:
    """移除 HTML/富文本标签（如 ``<b>左转</b>`` → ``左转``）。"""
    return re.sub(r"<[^>]+>", "", str(text or ""))


def _safe_int(value: Any) -> int:
    """安全转 int：解析失败 / 非法值返回 0。"""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    """安全转 float：解析失败 / 非法值返回 0.0。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_duration(seconds: Any) -> str:
    """把秒数格式化为 ``约 N 分钟`` / ``N 小时 M 分钟``。"""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "未知"
    if total <= 0:
        return "未知"
    if total < 60:
        return f"{total}秒"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}分钟"
    hours, mins = divmod(minutes, 60)
    return f"{hours}小时{mins}分钟"


def _fmt_distance(meters: Any) -> str:
    """把米数格式化为公里。"""
    try:
        km = float(meters) / 1000
    except (TypeError, ValueError):
        return "未知"
    return f"{km:.1f}公里"


class RouteResolutionError(ValueError):
    """地名无法解析为坐标（供上层转为可读的错误提示）。"""


def _is_coord(text: str) -> bool:
    """判断输入是否已是 ``经度,纬度`` 坐标（与既有约定一致：含逗号即视为坐标）。"""
    return "," in text


# 地理计算公共函数（坐标解析 / 球面距离）迁移至 src/tools/amap/geo.py，
# 此处保留私有别名以兼容既有调用方。
_parse_coord = parse_coord
_haversine_km = haversine_km


def order_spots_by_proximity(
    spots: list[str], coords: list[str]
) -> tuple[list[str], list[str]]:
    """按「最近邻贪心」重排景点顺序，减少往返绕路。

    从第一个景点出发，每步跳向距离当前点最近的未访问景点；
    坐标解析失败的条目按原相对顺序排在末尾。

    Returns:
        重排后的 ``(spots, coords)``，两个列表顺序一一对应。
    """
    n = len(spots)
    if n < 2 or len(coords) != n:
        return list(spots), list(coords)

    parsed = [_parse_coord(c) for c in coords]
    remaining = list(range(n))
    ordered_idx: list[int] = [remaining.pop(0)]  # 以第一个景点为起点
    while remaining:
        cur = parsed[ordered_idx[-1]]
        if cur is None:
            ordered_idx.append(remaining.pop(0))
            continue
        nearest = min(
            remaining,
            key=lambda i: _haversine_km(cur, parsed[i])
            if parsed[i] is not None
            else float("inf"),
        )
        remaining.remove(nearest)
        ordered_idx.append(nearest)

    return [spots[i] for i in ordered_idx], [coords[i] for i in ordered_idx]


class RouteTool:
    DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"
    TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"
    WALKING_URL = "https://restapi.amap.com/v3/direction/walking"

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @classmethod
    def _resolve_endpoint(cls, place: str, city: Optional[str], role: str) -> str:
        """把起点 / 终点统一解析为坐标。

        已是坐标直接返回；地名经地理编码，失败时抛出
        :class:`RouteResolutionError`，避免把原始地名静默传给高德
        ``direction/*``（其要求坐标，传地名只会返回参数错误）。
        """
        if _is_coord(place):
            return place
        coord = geocode.geocode_or_raw(place, city)
        if not _is_coord(coord):
            raise RouteResolutionError(f"无法定位{role}：「{place}」，请确认地名是否正确，或提供「经度,纬度」坐标。")
        return coord

    @classmethod
    def _request_route(
        cls, url: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """请求路线接口并校验高德 ``status``，失败时记录原因并返回 None。"""
        data = cached_json_get(url, params, cache_key=None)
        if data is None:
            return None
        if data.get("status") != "1":
            # 之前这里静默返回错误体，上层统一显示"暂无路线信息"，
            # 导致 geocode 失败 / 参数错误 / 无路线无法区分，LLM 无法据此调整。
            logger.warning("高德路线API错误 (%s): %s", url, data.get("info", "未知错误"))
            return None
        return data

    @classmethod
    async def _aresolve_endpoint(
        cls, place: str, city: Optional[str], role: str
    ) -> str:
        """:meth:`_resolve_endpoint` 的异步版本。"""
        if _is_coord(place):
            return place
        coord = await geocode.ageocode_or_raw(place, city)
        if not _is_coord(coord):
            raise RouteResolutionError(f"无法定位{role}：「{place}」，请确认地名是否正确，或提供「经度,纬度」坐标。")
        return coord

    @classmethod
    async def _arequest_route(
        cls, url: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """:meth:`_request_route` 的异步版本。"""
        data = await acached_json_get(url, params, cache_key=None)
        if data is None:
            return None
        if data.get("status") != "1":
            logger.warning("高德路线API错误 (%s): %s", url, data.get("info", "未知错误"))
            return None
        return data

    # ------------------------------------------------------------------
    # 驾车
    # ------------------------------------------------------------------
    @classmethod
    def get_driving_route(
        cls,
        origin: str,
        destination: str,
        city: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """查询驾车路线。

        Args:
            origin: 起点（地名或 ``经度,纬度``，地名将先经地理编码）。
            destination: 终点（同上）。
            city: 所在城市，用于提升地名解析准确性。

        Returns:
            高德原始响应 dict；地名无法定位抛 :class:`RouteResolutionError`，
            其余失败返回 None。
        """
        origin_coord = cls._resolve_endpoint(origin, city, "起点")
        dest_coord = cls._resolve_endpoint(destination, city, "终点")
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
        }
        return cls._request_route(cls.DRIVING_URL, params)

    @classmethod
    async def aget_driving_route(
        cls,
        origin: str,
        destination: str,
        city: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """:meth:`get_driving_route` 的异步版本（异常语义一致）。"""
        origin_coord = await cls._aresolve_endpoint(origin, city, "起点")
        dest_coord = await cls._aresolve_endpoint(destination, city, "终点")
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
        }
        return await cls._arequest_route(cls.DRIVING_URL, params)

    # ------------------------------------------------------------------
    # 公交
    # ------------------------------------------------------------------
    @classmethod
    def get_transit_route(
        cls, origin: str, destination: str, city: str
    ) -> Optional[dict[str, Any]]:
        """查询公交 / 地铁路线。

        Args:
            origin / destination: 地名或坐标，地名将先经地理编码。
            city: 所在城市（高德公交接口必填，可为 ``adcode``）。
        """
        origin_coord = cls._resolve_endpoint(origin, city, "起点")
        dest_coord = cls._resolve_endpoint(destination, city, "终点")
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
            "city": city,
        }
        return cls._request_route(cls.TRANSIT_URL, params)

    @classmethod
    async def aget_transit_route(
        cls, origin: str, destination: str, city: str
    ) -> Optional[dict[str, Any]]:
        """:meth:`get_transit_route` 的异步版本（异常语义一致）。"""
        origin_coord = await cls._aresolve_endpoint(origin, city, "起点")
        dest_coord = await cls._aresolve_endpoint(destination, city, "终点")
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
            "city": city,
        }
        return await cls._arequest_route(cls.TRANSIT_URL, params)

    # ------------------------------------------------------------------
    # 步行
    # ------------------------------------------------------------------
    @classmethod
    def get_walking_route(
        cls, origin: str, destination: str, city: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """获取步行路线。

        Args:
            origin: 起点坐标（经度,纬度）或地名。
            destination: 终点坐标（经度,纬度）或地名。
            city: 所在城市，用于地名解析。

        Returns:
            步行路线数据字典。
        """
        origin_coord = cls._resolve_endpoint(origin, city, "起点")
        dest_coord = cls._resolve_endpoint(destination, city, "终点")
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
        }
        return cls._request_route(cls.WALKING_URL, params)

    # ------------------------------------------------------------------
    # 格式化
    # ------------------------------------------------------------------
    @classmethod
    def format_driving_route(cls, route_data: dict[str, Any]) -> str:
        if not route_data or "route" not in route_data:
            return "暂无路线信息"

        route = route_data["route"]
        paths = route.get("paths", [])

        if not paths:
            return "暂无推荐路线"

        best_path = paths[0]
        duration = _fmt_duration(best_path.get("duration", 0))
        distance = _fmt_distance(best_path.get("distance", 0))

        result = "🚗 驾车路线规划：\n" f"⏱️ 预计时间：{duration}\n" f"🛣️ 总距离：{distance}\n" "📍 主要步骤："

        steps = best_path.get("steps", [])
        for idx, step in enumerate(steps[:8], 1):
            instruction = _strip_tags(step.get("instruction", ""))
            result += f"\n{idx}. {instruction}"

        if len(steps) > 8:
            result += f"\n... (还有{len(steps) - 8}个步骤)"

        return result

    @classmethod
    def format_transit_route(cls, route_data: dict[str, Any]) -> str:
        """格式化公交路线信息。"""
        if not route_data or "route" not in route_data:
            return "暂无公交路线信息"

        route = route_data["route"]
        transits = route.get("transits", [])

        if not transits:
            return "暂无公交路线信息"

        result = "🚌 公交路线规划：\n\n"
        for i, transit in enumerate(transits[:3], 1):
            result += f"方案{i}：\n"
            result += f"  预计时间：{_fmt_duration(transit.get('duration', 0))}\n"
            result += f"  步行距离：{_fmt_distance(transit.get('walking_distance', 0))}\n"

            # 解析换乘信息
            segments = transit.get("segments", [])
            transit_lines = []
            for seg in segments:
                if "bus" in seg and seg["bus"]:
                    buslines = seg["bus"].get("buslines", [])
                    for line in buslines:
                        transit_lines.append(line.get("name", "未知线路"))

            if transit_lines:
                result += f"  换乘线路：{' → '.join(transit_lines)}\n"
            result += "\n"

        return result

    @classmethod
    def format_walking_route(cls, route_data: dict[str, Any]) -> str:
        """格式化步行路线信息。"""
        if not route_data or "route" not in route_data:
            return "暂无步行路线信息"

        route = route_data["route"]
        paths = route.get("paths", [])

        if not paths:
            return "暂无步行路线信息"

        path = paths[0]

        result = "🚶 步行路线规划：\n\n"
        result += f"  总距离：{_fmt_distance(path.get('distance', 0))}\n"
        result += f"  预计时间：{_fmt_duration(path.get('duration', 0))}\n\n"

        # 步骤详情
        steps = path.get("steps", [])
        if steps:
            result += "  路线详情：\n"
            for i, step in enumerate(steps[:5], 1):
                instruction = _strip_tags(step.get("instruction", ""))
                result += f"    {i}. {instruction} ({_fmt_distance(step.get('distance', 0))})\n"

        return result

    # ------------------------------------------------------------------
    # 多景点路线
    # ------------------------------------------------------------------
    @classmethod
    def plan_multi_spot_route(
        cls,
        spots: list[str],
        city: str = "",
        mode: str = "driving",
        optimize_order: bool = False,
    ) -> Optional[dict[str, Any]]:
        """规划多个景点之间的路线，依次连接相邻景点。

        先对每个景点做**地理编码**，把地名转为坐标后再调用路线接口，
        修复了之前直接把地名传给高德 ``direction/*`` 导致静默失败的缺陷。

        Args:
            spots: 景点名称列表（至少 2 个）。
            city: 所在城市（公交模式必填，驾车模式可提升定位准确性）。
            mode: ``driving`` 或 ``transit``。
            optimize_order: 为 True 时按地理位置就近贪心重排游览顺序，
                减少往返绕路（结果中标注 ``optimized=True``）。

        返回各段路线和总体信息。
        """
        if len(spots) < 2:
            return {
                "error": "至少需要2个景点才能规划路线",
                "segments": [],
                "total_duration": 0,
                "total_distance": 0,
            }

        if mode == "transit" and not city:
            return {
                "error": "公交路线规划需要提供所在城市",
                "segments": [],
                "total_duration": 0,
                "total_distance": 0,
            }

        # 地名 -> 坐标（带缓存）
        resolved, failed = geocode.geocode_many(spots, city=city or None)
        if failed:
            return {
                "error": "以下景点无法定位，请提供更明确的名称：" + "、".join(failed),
                "segments": [],
                "total_duration": 0,
                "total_distance": 0,
            }

        optimized = False
        if optimize_order:
            spots, resolved = order_spots_by_proximity(spots, resolved)
            optimized = True

        segments = []
        total_duration_seconds = 0
        total_distance_meters = 0.0

        for i in range(len(resolved) - 1):
            origin_coord = resolved[i]
            dest_coord = resolved[i + 1]
            origin_name = spots[i]
            dest_name = spots[i + 1]

            if mode == "driving":
                route = cls.get_driving_route(
                    origin_coord, dest_coord, city=city or None
                )
            elif mode == "transit":
                route = cls.get_transit_route(origin_coord, dest_coord, city)
            else:
                continue

            if route and "route" in route:
                paths = route["route"].get("paths", [])
                if paths:
                    best = paths[0]
                    seg_seconds = _safe_int(best.get("duration", 0))
                    seg_meters = _safe_float(best.get("distance", 0))
                    total_duration_seconds += seg_seconds
                    total_distance_meters += seg_meters
                    segments.append(
                        {
                            "from": origin_name,
                            "to": dest_name,
                            "duration_minutes": max(seg_seconds // 60, 1),
                            "distance_km": round(seg_meters / 1000, 2),
                        }
                    )

        return {
            "segments": segments,
            "total_duration_minutes": max(total_duration_seconds // 60, 1)
            if total_duration_seconds
            else 0,
            # 向后兼容旧字段名
            "total_duration": max(total_duration_seconds // 60, 1)
            if total_duration_seconds
            else 0,
            "total_distance": round(total_distance_meters / 1000, 2),
            "spot_count": len(spots),
            "mode": mode,
            "optimized": optimized,
        }

    @classmethod
    def format_multi_spot_route(cls, plan_data: dict[str, Any]) -> str:
        if "error" in plan_data:
            return plan_data["error"]

        segments = plan_data.get("segments", [])
        if not segments:
            return "暂无路线规划信息"

        total_duration = plan_data.get(
            "total_duration_minutes", plan_data.get("total_duration", 0)
        )
        total_distance = plan_data.get("total_distance", 0)
        mode_label = {"driving": "驾车", "transit": "公交"}.get(
            plan_data.get("mode", ""), ""
        )

        lines = [
            f"\n🗺️ 多景点路线规划（{mode_label}）：",
            f"📍 共 {plan_data.get('spot_count', 0)} 个景点",
            f"⏱️ 总耗时：约 {total_duration} 分钟",
            f"🛣️ 总距离：{total_distance} 公里",
            "",
            "📋 各段路线：",
        ]

        for idx, seg in enumerate(segments, 1):
            lines.append(
                f"  {idx}. {seg['from']} → {seg['to']} | "
                f"{seg['duration_minutes']}分钟 | {seg['distance_km']}公里"
            )

        return "\n".join(lines)
