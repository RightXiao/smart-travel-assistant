from typing import Optional

from pydantic import BaseModel, Field


class WeatherInfo(BaseModel):
    city: str
    weather: str
    temperature: str
    wind_direction: str
    wind_power: str
    humidity: str
    report_time: str


class WeatherForecast(BaseModel):
    city: str
    forecasts: list[dict] = Field(default_factory=list)
    report_time: str = ""


class ScenicSpot(BaseModel):
    name: str
    address: str
    location: str
    rating: str = ""
    type_name: str = ""


class RouteStep(BaseModel):
    instruction: str
    road: str = ""
    distance: str = ""
    duration: str = ""


class RouteInfo(BaseModel):
    origin: str
    destination: str
    duration_minutes: int
    distance_km: float
    steps: list[RouteStep] = Field(default_factory=list)


class HotelInfo(BaseModel):
    name: str
    address: str
    location: str
    rating: str = ""
    price_range: str = ""
    type_name: str = ""


class FoodInfo(BaseModel):
    name: str
    address: str
    location: str
    rating: str = ""
    type_name: str = ""
    avg_price: str = ""


class DayPlan(BaseModel):
    day: int
    title: str = ""
    spots: list[str] = Field(default_factory=list)
    meals: list[str] = Field(default_factory=list)
    hotel: str = ""
    tips: str = ""


class TravelPlan(BaseModel):
    destination: str
    days: int
    budget: str
    weather: Optional[WeatherInfo] = None
    day_plans: list[DayPlan] = Field(default_factory=list)
    food_recommendations: list[str] = Field(default_factory=list)
    hotel_recommendations: list[str] = Field(default_factory=list)
    general_tips: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    chat_history: list[ChatMessage] = Field(default_factory=list)


class MultiSpotRouteRequest(BaseModel):
    spots: list[str] = Field(min_length=2, description="景点名称列表（至少 2 个）")
    city: str = ""
    mode: str = "driving"


class ChatResponse(BaseModel):
    response: str
