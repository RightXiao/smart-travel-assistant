import requests
from typing import Dict, Any, Optional
from src.config.settings import settings
from src.utils.logger import logger


class WeatherTool:
    BASE_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

    @classmethod
    def get_weather(cls, city: str, extensions: str = "base") -> Optional[Dict[str, Any]]:
        params = {
            "key": settings.AMAP_API_KEY,
            "city": city,
            "extensions": extensions,
        }
        try:
            response = requests.get(cls.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "1":
                return data
            logger.error(f"高德天气API错误: {data.get('info', '未知错误')}")
            return None
        except requests.RequestException as e:
            logger.error(f"请求天气信息失败: {e}")
            return None

    @classmethod
    def get_weather_forecast(cls, city: str) -> Optional[Dict[str, Any]]:
        """获取未来4天天气预报"""
        return cls.get_weather(city, extensions="all")

    @classmethod
    def format_weather_info(cls, weather_data: Dict[str, Any]) -> str:
        if not weather_data or "lives" not in weather_data:
            return "暂无天气信息"

        lives = weather_data["lives"][0]
        result = f"""
🌤️ 实时天气：
📍 城市：{lives.get('city', '未知')}
🌡️ 天气：{lives.get('weather', '未知')}
🌡️ 温度：{lives.get('temperature', '未知')}℃
💨 风向：{lives.get('winddirection', '未知')}风
💨 风力：{lives.get('windpower', '未知')}级
💧 湿度：{lives.get('humidity', '未知')}%
🕐 发布时间：{lives.get('reporttime', '未知')}
""".strip()
        return result

    @classmethod
    def format_forecast_info(cls, weather_data: Dict[str, Any]) -> str:
        if not weather_data or "forecasts" not in weather_data:
            return "暂无天气预报信息"

        forecasts = weather_data["forecasts"][0]
        casts = forecasts.get("casts", [])
        if not casts:
            return "暂无天气预报信息"

        lines = [f"\n📅 {forecasts.get('city', '未知')} 未来天气预报："]
        for cast in casts:
            date = cast.get("date", "")
            week_map = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "日"}
            week = week_map.get(str(cast.get("week", "")), "")
            day_weather = cast.get("dayweather", "")
            night_weather = cast.get("nightweather", "")
            day_temp = cast.get("daytemp", "")
            night_temp = cast.get("nighttemp", "")
            day_wind = cast.get("daywind", "")
            day_power = cast.get("daypower", "")
            lines.append(
                f"{date} 周{week} | ☀️ 白天：{day_weather} {day_temp}℃ {day_wind}{day_power}级"
                f" | 🌙 夜间：{night_weather} {night_temp}℃"
            )

        return "\n".join(lines)

    @classmethod
    def get_dressing_advice(cls, weather_data: Dict[str, Any]) -> str:
        """根据天气数据生成穿搭建议"""
        if not weather_data or "lives" not in weather_data:
            return ""
        live = weather_data["lives"][0]
        temp_str = live.get("temperature", "")
        weather = live.get("weather", "")
        wind = live.get("windpower", "")

        try:
            temp = float(temp_str)
        except (ValueError, TypeError):
            temp = 20

        try:
            wind_power = float(wind)
        except (ValueError, TypeError):
            wind_power = 2

        # 基于温度给出穿搭建议
        if temp >= 30:
            base = "天气炎热，建议穿着短袖、短裤、裙子等轻薄透气的衣物，注意防晒"
        elif temp >= 25:
            base = "天气温暖，建议穿着短袖、薄长裤，可备薄外套防晒"
        elif temp >= 20:
            base = "气温舒适，建议穿着长袖T恤、薄外套或衬衫，搭配长裤"
        elif temp >= 15:
            base = "天气微凉，建议穿着薄毛衣、卫衣或夹克，搭配长裤"
        elif temp >= 10:
            base = "天气较凉，建议穿着毛衣、厚外套或风衣"
        elif temp >= 5:
            base = "天气冷，建议穿着羽绒服、棉衣、厚毛衣，注意保暖"
        else:
            base = "天气寒冷，建议穿着厚羽绒服、棉衣、围巾、手套等保暖衣物"

        if "雨" in weather:
            base += "；有降雨，请携带雨具，穿防滑鞋"
        if wind_power >= 4:
            base += "；风力较大，建议穿着防风外套"

        return base
