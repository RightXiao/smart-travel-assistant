from typing import Optional
from fastapi import FastAPI
from src.models.travel import ChatRequest, ChatResponse

app = FastAPI(
    title="智能旅行助手 API",
    description="基于 LangChain + GLM + 高德地图的智能旅行助手 RESTful API",
    version="1.0.0",
)


@app.get("/")
def root():
    return {"name": "智能旅行助手 API", "version": "1.0.0", "status": "running"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    from src.agents.travel_assistant import TravelAssistant

    assistant = TravelAssistant()
    history_dicts = [m.model_dump() if hasattr(m, "model_dump") else m for m in request.chat_history]
    response_text = assistant.chat(request.message, chat_history=history_dicts)
    return ChatResponse(response=response_text)


@app.get("/weather/{city}")
def get_weather(city: str, forecast: bool = False):
    from src.tools.amap.weather import WeatherTool

    if forecast:
        data = WeatherTool.get_weather_forecast(city)
        if data:
            return {"status": "ok", "data": WeatherTool.format_forecast_info(data)}
    else:
        data = WeatherTool.get_weather(city)
        if data:
            weather_info = WeatherTool.format_weather_info(data)
            dressing = WeatherTool.get_dressing_advice(data)
            return {"status": "ok", "data": {"weather": weather_info, "dressing_advice": dressing}}
    return {"status": "error", "message": "无法查询天气信息"}


@app.get("/spots/{city}")
def get_spots(city: str, page_size: int = 10):
    from src.tools.amap.poi import POITool

    data = POITool.search_scenic_spots(city, page_size=page_size)
    if data and "pois" in data:
        return {"status": "ok", "count": len(data["pois"]), "data": data["pois"]}
    return {"status": "error", "message": "无法查询景点信息"}


@app.get("/food/{city}")
def get_food(city: str, page_size: int = 10):
    from src.tools.amap.poi import POITool

    data = POITool.search_food(city, page_size=page_size)
    if data and "pois" in data:
        return {"status": "ok", "count": len(data["pois"]), "data": data["pois"]}
    return {"status": "error", "message": "无法查询美食信息"}


@app.get("/hotels/{city}")
def get_hotels(city: str, budget: Optional[str] = None, page_size: int = 10):
    from src.tools.amap.poi import POITool

    if budget:
        data = POITool.search_hotel_by_budget(city, budget, page_size=page_size)
    else:
        data = POITool.search_hotel(city, page_size=page_size)
    if data and "pois" in data:
        return {"status": "ok", "count": len(data["pois"]), "data": data["pois"]}
    return {"status": "error", "message": "无法查询住宿信息"}


@app.get("/route/driving")
def get_driving_route(origin: str, destination: str):
    from src.tools.amap.route import RouteTool

    data = RouteTool.get_driving_route(origin, destination)
    if data and "route" in data:
        return {"status": "ok", "data": RouteTool.format_driving_route(data)}
    return {"status": "error", "message": "无法查询驾车路线"}


@app.get("/route/transit")
def get_transit_route(origin: str, destination: str, city: str):
    from src.tools.amap.route import RouteTool

    data = RouteTool.get_transit_route(origin, destination, city)
    if data and "route" in data:
        return {"status": "ok", "data": RouteTool.format_driving_route(data)}
    return {"status": "error", "message": "无法查询公交路线"}


@app.post("/route/multi-spot")
def plan_multi_spot_route(spots: list[str], city: str = "", mode: str = "driving"):
    from src.tools.amap.route import RouteTool

    data = RouteTool.plan_multi_spot_route(spots, city=city, mode=mode)
    if data:
        return {"status": "ok", "data": RouteTool.format_multi_spot_route(data)}
    return {"status": "error", "message": "无法规划多景点路线"}
