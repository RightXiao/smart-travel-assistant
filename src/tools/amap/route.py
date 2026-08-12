import re
from typing import Any, Dict, List, Optional

from src.config.settings import get_settings
from src.tools.amap import geocode
from src.utils.http import cached_json_get


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


class RouteTool:
    DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"
    TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"
    WALKING_URL = "https://restapi.amap.com/v3/direction/walking"

    # ------------------------------------------------------------------
    # 驾车
    # ------------------------------------------------------------------
    @classmethod
    def get_driving_route(
        cls,
        origin: str,
        destination: str,
        city: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """查询驾车路线。

        Args:
            origin: 起点（地名或 ``经度,纬度``，地名将先经地理编码）。
            destination: 终点（同上）。
            city: 所在城市，用于提升地名解析准确性。

        Returns:
            高德原始响应 dict，失败返回 None。
        """
        # 起终点已是坐标（含逗号）则直接使用，否则做地理编码
        origin_coord = origin if "," in origin else geocode.geocode_or_raw(origin, city)
        dest_coord = (
            destination if "," in destination else geocode.geocode_or_raw(destination, city)
        )
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
        }
        return cached_json_get(cls.DRIVING_URL, params, cache_key=None)

    # ------------------------------------------------------------------
    # 公交
    # ------------------------------------------------------------------
    @classmethod
    def get_transit_route(
        cls, origin: str, destination: str, city: str
    ) -> Optional[Dict[str, Any]]:
        """查询公交 / 地铁路线。

        Args:
            origin / destination: 地名或坐标，地名将先经地理编码。
            city: 所在城市（高德公交接口必填，可为 ``adcode``）。
        """
        origin_coord = origin if "," in origin else geocode.geocode_or_raw(origin, city)
        dest_coord = (
            destination if "," in destination else geocode.geocode_or_raw(destination, city)
        )
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
            "city": city,
        }
        return cached_json_get(cls.TRANSIT_URL, params, cache_key=None)

    # ------------------------------------------------------------------
    # 步行
    # ------------------------------------------------------------------
    @classmethod
    def get_walking_route(
        cls, origin: str, destination: str, city: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取步行路线。

        Args:
            origin: 起点坐标（经纬度，格式：经度,纬度）或地名。
            destination: 终点坐标（经纬度，格式：经度,纬度）或地名。
            city: 所在城市，用于地名解析。

        Returns:
            步行路线数据字典。
        """
        origin_coord = origin if "," in origin else geocode.geocode_or_raw(origin, city)
        dest_coord = (
            destination if "," in destination else geocode.geocode_or_raw(destination, city)
        )
        params = {
            "key": get_settings().AMAP_API_KEY,
            "origin": origin_coord,
            "destination": dest_coord,
        }
        return cached_json_get(cls.WALKING_URL, params, cache_key=None)

    # ------------------------------------------------------------------
    # 格式化
    # ------------------------------------------------------------------
    @classmethod
    def format_driving_route(cls, route_data: Dict[str, Any]) -> str:
        if not route_data or "route" not in route_data:
            return "暂无路线信息"

        route = route_data["route"]
        paths = route.get("paths", [])

        if not paths:
            return "暂无推荐路线"

        best_path = paths[0]
        duration = _fmt_duration(best_path.get("duration", 0))
        distance = _fmt_distance(best_path.get("distance", 0))

        result = (
            "🚗 驾车路线规划：\n"
            f"⏱️ 预计时间：{duration}\n"
            f"🛣️ 总距离：{distance}\n"
            "📍 主要步骤："
        )

        steps = best_path.get("steps", [])
        for idx, step in enumerate(steps[:8], 1):
            instruction = _strip_tags(step.get("instruction", ""))
            result += f"\n{idx}. {instruction}"

        if len(steps) > 8:
            result += f"\n... (还有{len(steps) - 8}个步骤)"

        return result

    @classmethod
    def format_transit_route(cls, route_data: Dict[str, Any]) -> str:
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
    def format_walking_route(cls, route_data: Dict[str, Any]) -> str:
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
        spots: List[str],
        city: str = "",
        mode: str = "driving",
    ) -> Optional[Dict[str, Any]]:
        """规划多个景点之间的路线，依次连接相邻景点。

        现在会先对每个景点做**地理编码**，把地名转为坐标后再调用路线接口，
        修复了之前直接把地名传给高德 ``direction/*`` 导致静默失败的缺陷。

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

        segments = []
        total_duration_seconds = 0
        total_distance_meters = 0.0

        for i in range(len(resolved) - 1):
            origin_coord = resolved[i]
            dest_coord = resolved[i + 1]
            origin_name = spots[i]
            dest_name = spots[i + 1]

            if mode == "driving":
                route = cls.get_driving_route(origin_coord, dest_coord, city=city or None)
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
        }

    @classmethod
    def format_multi_spot_route(cls, plan_data: Dict[str, Any]) -> str:
        if "error" in plan_data:
            return plan_data["error"]

        segments = plan_data.get("segments", [])
        if not segments:
            return "暂无路线规划信息"

        total_duration = plan_data.get("total_duration_minutes", plan_data.get("total_duration", 0))
        total_distance = plan_data.get("total_distance", 0)
        mode_label = {"driving": "驾车", "transit": "公交"}.get(plan_data.get("mode", ""), "")

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
