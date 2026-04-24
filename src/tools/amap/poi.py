import requests
from typing import Dict, Any, Optional, List
from src.config.settings import settings


class POITool:
    BASE_URL = "https://restapi.amap.com/v5/place/text"
    
    @classmethod
    def search_poi(cls, keywords: str, city: Optional[str] = None, 
                   types: Optional[str] = None, page_size: int = 10) -> Optional[Dict[str, Any]]:
        params = {
            "key": settings.AMAP_API_KEY,
            "keywords": keywords,
            "page_size": page_size
        }
        
        if city:
            params["city"] = city
        if types:
            params["types"] = types
        
        try:
            response = requests.get(cls.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "1":
                return data
            else:
                print(f"高德POI搜索API错误: {data.get('info', '未知错误')}")
                return None
        except requests.RequestException as e:
            print(f"POI搜索请求失败: {e}")
            return None
    
    @classmethod
    def search_scenic_spots(cls, city: str, page_size: int = 10) -> Optional[Dict[str, Any]]:
        return cls.search_poi(keywords="景点", city=city, types="110000", page_size=page_size)
    
    @classmethod
    def search_food(cls, city: str, page_size: int = 10) -> Optional[Dict[str, Any]]:
        return cls.search_poi(keywords="美食", city=city, types="050000", page_size=page_size)
    
    @classmethod
    def search_hotel(cls, city: str, page_size: int = 10) -> Optional[Dict[str, Any]]:
        return cls.search_poi(keywords="酒店", city=city, types="100000", page_size=page_size)

    @classmethod
    def search_hotel_by_budget(cls, city: str, budget: str = "", page_size: int = 10) -> Optional[Dict[str, Any]]:
        """
        根据预算搜索酒店。
        budget 可以是 '经济型'(<300), '舒适型'(300-600), '高档型'(600-1000), '豪华型'(>1000)
        """
        budget_lower = budget.strip().lower() if budget else ""
        keyword_map = {
            "经济型": "经济型酒店 快捷酒店 青年旅舍",
            "经济": "经济型酒店 快捷酒店 青年旅舍",
            "舒适型": "舒适型酒店 商务酒店 三星酒店",
            "舒适": "舒适型酒店 商务酒店 三星酒店",
            "高档型": "高档酒店 四星级酒店",
            "高档": "高档酒店 四星级酒店",
            "豪华型": "豪华酒店 五星级酒店 度假酒店",
            "豪华": "豪华酒店 五星级酒店 度假酒店",
        }

        keywords = keyword_map.get(budget_lower, "酒店")
        return cls.search_poi(keywords=keywords, city=city, types="100000", page_size=page_size)

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
