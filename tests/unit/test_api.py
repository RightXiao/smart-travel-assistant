from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    """构造 TestClient，并把 get_assistant 单例复位以隔离测试。"""
    import src.api as api

    api._assistant_instance = None
    return TestClient(api.app)


class TestRoot:
    def test_root(self):
        resp = _client().get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"


class TestChat:
    def test_chat(self):
        with patch("src.agents.travel_assistant.TravelAssistant") as MockAsst:
            MockAsst.return_value.chat.return_value = "助手回复"
            resp = _client().post(
                "/chat",
                json={"message": "你好", "chat_history": []},
            )
            assert resp.status_code == 200
            assert resp.json() == {"response": "助手回复"}


class TestWeather:
    def test_weather(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather") as m_weather, \
             patch("src.tools.amap.weather.WeatherTool.format_weather_info") as m_fmt, \
             patch("src.tools.amap.weather.WeatherTool.get_dressing_advice") as m_dress:
            m_weather.return_value = {"lives": []}
            m_fmt.return_value = "晴 25℃"
            m_dress.return_value = "短袖"
            resp = _client().get("/weather/北京")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["data"]["weather"] == "晴 25℃"

    def test_weather_error(self):
        with patch("src.tools.amap.weather.WeatherTool.get_weather", return_value=None):
            resp = _client().get("/weather/北京")
            assert resp.status_code == 200
            assert resp.json()["status"] == "error"


class TestPOI:
    def test_spots(self):
        with patch("src.tools.amap.poi.POITool.search_scenic_spots") as m:
            m.return_value = {"pois": [{"name": "故宫"}]}
            resp = _client().get("/spots/北京")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["count"] == 1

    def test_hotels_with_budget(self):
        with patch("src.tools.amap.poi.POITool.search_hotel_by_budget") as m:
            m.return_value = {"pois": [{"name": "如家"}]}
            resp = _client().get("/hotels/北京", params={"budget": "经济型"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


class TestRoute:
    def test_driving(self):
        with patch("src.tools.amap.route.RouteTool.get_driving_route") as m, \
             patch("src.tools.amap.route.RouteTool.format_driving_route") as m_fmt:
            m.return_value = {"route": {"paths": []}}
            m_fmt.return_value = "驾车路线"
            resp = _client().get(
                "/route/driving", params={"origin": "a", "destination": "b"}
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_transit(self):
        with patch("src.tools.amap.route.RouteTool.get_transit_route") as m, \
             patch("src.tools.amap.route.RouteTool.format_transit_route") as m_fmt:
            m.return_value = {"route": {"transits": []}}
            m_fmt.return_value = "公交路线"
            resp = _client().get(
                "/route/transit",
                params={"origin": "a", "destination": "b", "city": "北京"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_multi_spot(self):
        with patch("src.tools.amap.route.RouteTool.plan_multi_spot_route") as m, \
             patch("src.tools.amap.route.RouteTool.format_multi_spot_route") as m_fmt:
            m.return_value = {"segments": []}
            m_fmt.return_value = "多景点路线"
            resp = _client().post(
                "/route/multi-spot",
                params={"spots": ["天安门", "故宫"], "city": "北京"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
