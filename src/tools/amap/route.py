import requests
from typing import Dict, Any, Optional, List, Tuple
from src.config.settings import settings


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
                print(f"高德驾车路线API错误: {data.get('info', '未知错误')}")
                return None
        except requests.RequestException as e:
            print(f"驾车路线请求失败: {e}")
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
                print(f"高德公交路线API错误: {data.get('info', '未知错误')}")
                return None
        except requests.RequestException as e:
            print(f"公交路线请求失败: {e}")
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
