import requests
from typing import Dict, Any, Optional, List, Tuple
from src.config.settings import settings
from src.utils.logger import logger


class RouteTool:
    DRIVING_URL = "https://restapi.amap.com/v3/direction/driving"
    TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"
    WALKING_URL = "https://restapi.amap.com/v3/direction/walking"
    
    @classmethod
    def get_driving_route(cls, origin: str, destination: str, 
                           origin_city: Optional[str] = None, 
                           destination_city: Optional[str] = None) -> Optional[Dict[str, Any]]:
        params = {
            "key": settings.AMAP_API_KEY,
            "origin": origin,
            "destination": destination
        }
        
        if origin_city:
            params["originid"] = origin_city
        if destination_city:
            params["destinationid"] = destination_city
        
        try:
            response = requests.get(cls.DRIVING_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "1":
                return data
            else:
                logger.error(f"高德驾车路线API错误: {data.get('info', '未知错误')}")
                return None
        except requests.RequestException as e:
            logger.error(f"驾车路线请求失败: {e}")
            return None
    
    @classmethod
    def get_transit_route(cls, origin: str, destination: str, city: str) -> Optional[Dict[str, Any]]:
        params = {
            "key": settings.AMAP_API_KEY,
            "origin": origin,
            "destination": destination,
            "city": city
        }
        
        try:
            response = requests.get(cls.TRANSIT_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "1":
                return data
            else:
                logger.error(f"高德公交路线API错误: {data.get('info', '未知错误')}")
                return None
        except requests.RequestException as e:
            logger.error(f"公交路线请求失败: {e}")
            return None
    
    @classmethod
    def format_driving_route(cls, route_data: Dict[str, Any]) -> str:
        if not route_data or "route" not in route_data:
            return "暂无路线信息"
        
        route = route_data["route"]
        paths = route.get("paths", [])
        
        if not paths:
            return "暂无推荐路线"
        
        best_path = paths[0]
        duration = int(best_path.get("duration", 0)) // 60
        distance = float(best_path.get("distance", 0)) / 1000
        
        result = f"""
🚗 驾车路线规划：
⏱️ 预计时间：{duration}分钟
🛣️ 总距离：{distance:.2f}公里
📍 主要步骤：
        """.strip()
        
        steps = best_path.get("steps", [])
        for idx, step in enumerate(steps[:8], 1):
            instruction = step.get("instruction", "").replace("<", "").replace(">", "")
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
            result += f"  预计时间：{transit.get('duration', '未知')}秒\n"
            result += f"  步行距离：{transit.get('walking_distance', '未知')}米\n"
            
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
    def get_walking_route(cls, origin: str, destination: str) -> Optional[Dict[str, Any]]:
        """获取步行路线。
        
        Args:
            origin: 起点坐标（经纬度，格式：经度,纬度）。
            destination: 终点坐标（经纬度，格式：经度,纬度）。
            
        Returns:
            步行路线数据字典。
        """
        params = {
            "key": settings.AMAP_API_KEY,
            "origin": origin,
            "destination": destination,
        }
        
        try:
            response = requests.get(cls.WALKING_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "1":
                return data
            else:
                logger.error(f"高德步行路线API错误: {data.get('info', '未知错误')}")
                return None
        except requests.RequestException as e:
            logger.error(f"步行路线请求失败: {e}")
            return None

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
        distance = int(path.get("distance", 0))
        duration = int(path.get("duration", 0))
        
        # 转换距离和时间
        distance_km = distance / 1000
        duration_min = duration / 60
        
        result = f"🚶 步行路线规划：\n\n"
        result += f"  总距离：{distance_km:.1f}公里\n"
        result += f"  预计时间：{duration_min:.0f}分钟\n\n"
        
        # 步骤详情
        steps = path.get("steps", [])
        if steps:
            result += "  路线详情：\n"
            for i, step in enumerate(steps[:5], 1):
                instruction = step.get("instruction", "")
                step_distance = int(step.get("distance", 0))
                result += f"    {i}. {instruction} ({step_distance}米)\n"
        
        return result

    @classmethod
    def plan_multi_spot_route(cls, spots: list[str], city: str = "",
                              mode: str = "driving") -> Optional[Dict[str, Any]]:
        """
        规划多个景点之间的路线，依次连接相邻景点。
        返回各段路线和总体信息。
        """
        if len(spots) < 2:
            return {"error": "至少需要2个景点才能规划路线", "segments": [], "total_duration": 0, "total_distance": 0}

        segments = []
        total_duration = 0
        total_distance = 0.0

        for i in range(len(spots) - 1):
            origin = spots[i]
            destination = spots[i + 1]

            if mode == "driving":
                route = cls.get_driving_route(origin, destination)
            elif mode == "transit":
                route = cls.get_transit_route(origin, destination, city)
            else:
                continue

            if route and "route" in route:
                paths = route["route"].get("paths", [])
                if paths:
                    best = paths[0]
                    segment_time = int(best.get("duration", 0)) // 60
                    segment_dist = float(best.get("distance", 0)) / 1000
                    total_duration += segment_time
                    total_distance += segment_dist
                    segments.append({
                        "from": origin,
                        "to": destination,
                        "duration_minutes": segment_time,
                        "distance_km": round(segment_dist, 2),
                    })

        return {
            "segments": segments,
            "total_duration": total_duration,
            "total_distance": round(total_distance, 2),
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

        total_duration = plan_data.get("total_duration", 0)
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
