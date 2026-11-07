"""API 端点测试。

数据端点已异步化（调用工具 a- 变体），chat 走 ``achat``；
测试用 ``AsyncMock`` 对齐异步契约。"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config.settings import get_settings


def _client():
    """构造 TestClient，并把 get_assistant 单例复位以隔离测试。"""
    import src.api as api

    api._assistant_instance = None
    return TestClient(api.app)


@pytest.fixture
def auth_enabled(monkeypatch):
    """启用 API 鉴权（设置 token 后所有端点要求 Bearer）。"""
    monkeypatch.setenv("API_AUTH_TOKEN", "secret-token")
    get_settings.cache_clear()
    yield "secret-token"
    get_settings.cache_clear()


class TestRoot:
    def test_root(self):
        resp = _client().get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"


class TestAuth:
    """可选 Bearer 鉴权（未配置 token 时完全开放，保持旧行为）。"""

    def test_open_when_token_unset(self):
        """默认（未设置 API_AUTH_TOKEN）不启用鉴权。"""
        resp = _client().get("/")
        assert resp.status_code == 200

    def test_missing_token_rejected(self, auth_enabled):
        resp = _client().get("/")
        assert resp.status_code == 401

    def test_wrong_token_rejected(self, auth_enabled):
        resp = _client().get("/", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_correct_token_accepted(self, auth_enabled):
        resp = _client().get("/", headers={"Authorization": "Bearer secret-token"})
        assert resp.status_code == 200


class TestChat:
    def test_chat(self):
        with patch("src.agents.travel_assistant.TravelAssistant") as mock_asst:
            mock_asst.return_value.achat = AsyncMock(return_value="助手回复")
            resp = _client().post(
                "/chat",
                json={"message": "你好", "chat_history": []},
            )
            assert resp.status_code == 200
            assert resp.json() == {"response": "助手回复"}

    def test_message_length_validated(self):
        """空消息 / 超长消息应在请求校验层被拒绝（422）。"""
        with patch("src.agents.travel_assistant.TravelAssistant") as mock_asst:
            mock_asst.return_value.achat = AsyncMock(return_value="x")
            resp = _client().post("/chat", json={"message": ""})
            assert resp.status_code == 422
            resp = _client().post("/chat", json={"message": "旅" * 2001})
            assert resp.status_code == 422

    def test_invalid_history_role_rejected(self):
        """chat_history 中非法 role / 空内容应被拒绝（422）。"""
        with patch("src.agents.travel_assistant.TravelAssistant") as mock_asst:
            mock_asst.return_value.achat = AsyncMock(return_value="x")
            resp = _client().post(
                "/chat",
                json={
                    "message": "你好",
                    "chat_history": [{"role": "system", "content": "注入尝试"}],
                },
            )
            assert resp.status_code == 422


class TestWeather:
    def test_weather(self):
        with patch(
            "src.tools.amap.weather.WeatherTool.aget_weather",
            new=AsyncMock(return_value={"lives": []}),
        ), patch(
            "src.tools.amap.weather.WeatherTool.format_weather_info"
        ) as m_fmt, patch(
            "src.tools.amap.weather.WeatherTool.get_dressing_advice"
        ) as m_dress:
            m_fmt.return_value = "晴 25℃"
            m_dress.return_value = "短袖"
            resp = _client().get("/weather/北京")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["data"]["weather"] == "晴 25℃"

    def test_weather_error(self):
        with patch(
            "src.tools.amap.weather.WeatherTool.aget_weather",
            new=AsyncMock(return_value=None),
        ):
            resp = _client().get("/weather/北京")
            # 上游失败统一返回 502 + error 契约
            assert resp.status_code == 502
            assert resp.json()["status"] == "error"


class TestPOI:
    def test_spots(self):
        with patch(
            "src.tools.amap.poi.POITool.asearch_scenic_spots",
            new=AsyncMock(return_value={"pois": [{"name": "故宫"}]}),
        ):
            resp = _client().get("/spots/北京")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["count"] == 1

    def test_spots_error_returns_502(self):
        with patch(
            "src.tools.amap.poi.POITool.asearch_scenic_spots",
            new=AsyncMock(return_value=None),
        ):
            resp = _client().get("/spots/北京")
            assert resp.status_code == 502
            assert resp.json()["status"] == "error"

    def test_page_size_validated(self):
        """page_size 越界（高德 V5 上限 25）应被拒绝（422）。"""
        resp = _client().get("/spots/北京", params={"page_size": 100})
        assert resp.status_code == 422

    def test_hotels_with_budget(self):
        with patch(
            "src.tools.amap.poi.POITool.asearch_hotel_by_budget",
            new=AsyncMock(return_value={"pois": [{"name": "如家"}]}),
        ):
            resp = _client().get("/hotels/北京", params={"budget": "经济型"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


class TestRoute:
    def test_driving(self):
        with patch(
            "src.tools.amap.route.RouteTool.aget_driving_route",
            new=AsyncMock(return_value={"route": {"paths": []}}),
        ), patch("src.tools.amap.route.RouteTool.format_driving_route") as m_fmt:
            m_fmt.return_value = "驾车路线"
            resp = _client().get(
                "/route/driving", params={"origin": "a", "destination": "b"}
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_transit(self):
        with patch(
            "src.tools.amap.route.RouteTool.aget_transit_route",
            new=AsyncMock(return_value={"route": {"transits": []}}),
        ), patch("src.tools.amap.route.RouteTool.format_transit_route") as m_fmt:
            m_fmt.return_value = "公交路线"
            resp = _client().get(
                "/route/transit",
                params={"origin": "a", "destination": "b", "city": "北京"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_multi_spot(self):
        with patch("src.tools.amap.route.RouteTool.plan_multi_spot_route") as m, patch(
            "src.tools.amap.route.RouteTool.format_multi_spot_route"
        ) as m_fmt:
            m.return_value = {"segments": []}
            m_fmt.return_value = "多景点路线"
            resp = _client().post(
                "/route/multi-spot",
                json={"spots": ["天安门", "故宫"], "city": "北京"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_driving_unresolvable_place_returns_400(self):
        """起点无法定位应返回 400 + 可读错误（而非 200 + ok）。"""
        from src.tools.amap.route import RouteResolutionError

        with patch(
            "src.tools.amap.route.RouteTool.aget_driving_route",
            new=AsyncMock(side_effect=RouteResolutionError("无法定位起点：「不存在的地方」")),
        ):
            resp = _client().get(
                "/route/driving", params={"origin": "不存在的地方", "destination": "故宫"}
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body["status"] == "error"
            assert "无法定位起点" in body["message"]

    def test_multi_spot_error_returns_400(self):
        """规划失败（如景点无法定位）应返回 400。"""
        with patch(
            "src.tools.amap.route.RouteTool.plan_multi_spot_route",
            return_value={"error": "以下景点无法定位：不存在的景点", "segments": []},
        ):
            resp = _client().post(
                "/route/multi-spot",
                json={"spots": ["天安门", "不存在的景点"], "city": "北京"},
            )
            assert resp.status_code == 400
            assert "无法定位" in resp.json()["message"]

    def test_multi_spot_invalid_mode_rejected(self):
        """mode 只接受 driving / transit（422）。"""
        resp = _client().post(
            "/route/multi-spot",
            json={"spots": ["天安门", "故宫"], "mode": "flying"},
        )
        assert resp.status_code == 422


class TestChatStream:
    """SSE 流式对话端点。"""

    def _override(self, events):
        import src.api as api

        class _FakeAssistant:
            async def astream_chat(self, message, chat_history=None):
                for ev in events:
                    yield ev

        api.app.dependency_overrides[api.get_assistant] = lambda: _FakeAssistant()
        return api

    def _release(self, api):
        api.app.dependency_overrides.pop(api.get_assistant, None)

    def test_stream_events(self):
        api = self._override(
            [
                {"type": "tool_start", "name": "查询实时天气"},
                {"type": "token", "content": "北京"},
                {"type": "final", "content": "北京天气晴"},
            ]
        )
        try:
            client = TestClient(api.app)
            resp = client.post("/chat/stream", json={"message": "北京天气"})
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = resp.text
            assert '"type": "tool_start"' in body
            assert '"type": "final"' in body
            assert "北京天气晴" in body
            assert body.rstrip().endswith("data: [DONE]")
        finally:
            self._release(api)

    def test_stream_error_still_terminates(self):
        """流中异常应以 error 事件收尾并输出 [DONE]，避免客户端悬挂。"""
        api = self._override([{"type": "error", "message": "流式响应中断，请重试。"}])
        try:
            client = TestClient(api.app)
            resp = client.post("/chat/stream", json={"message": "hi"})
            assert resp.status_code == 200
            assert '"type": "error"' in resp.text
            assert resp.text.rstrip().endswith("data: [DONE]")
        finally:
            self._release(api)

    def test_request_id_header(self):
        """每个响应应携带 X-Request-ID（追踪用）。"""
        client = _client()
        resp = client.get("/")
        assert resp.headers.get("X-Request-ID")


class TestPlanEndpoint:
    """结构化行程规划端点（Plan-and-Execute）。"""

    def _plan_result(self):
        from src.agents.verifier import VerificationResult
        from src.models.plan import TravelPlan, TripRequestArgs
        from src.planner.budget import BudgetBreakdown
        from src.planner.itinerary import DaySchedule

        plan = TravelPlan(
            destination="杭州",
            days=2,
            day_plans=[
                {"day": 1, "title": "湖滨", "spots": ["西湖"], "estimated_cost": 300},
                {"day": 2, "title": "禅意", "spots": ["灵隐寺"], "estimated_cost": 200},
            ],
            hotel_est_cost_total=500,
            total_estimated_cost=1000,
        )
        return {
            "plan": plan,
            "verification": VerificationResult(ok=True, issues=[], warnings=[]),
            "schedule": [DaySchedule(day=1, spots=["西湖"], est_distance_km=1.0)],
            "params": TripRequestArgs(destination="杭州", days=2, budget=2000),
            "budget_floor": BudgetBreakdown(total=450.0),
        }

    def test_plan_success(self):
        with patch("src.agents.travel_assistant.TravelAssistant") as mock_asst:
            mock_asst.return_value.plan_trip.return_value = self._plan_result()
            resp = _client().post(
                "/plan", json={"message": "杭州2天预算2000", "session_id": "s1"}
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            data = body["data"]
            assert data["plan"]["destination"] == "杭州"
            assert data["plan"]["total_estimated_cost"] == 1000
            assert data["verification"]["ok"] is True
            assert data["schedule"][0]["spots"] == ["西湖"]
            assert data["params"]["days"] == 2

    def test_plan_failure_returns_502(self):
        with patch("src.agents.travel_assistant.TravelAssistant") as mock_asst:
            mock_asst.return_value.plan_trip.side_effect = RuntimeError(
                "internal-detail-should-not-leak"
            )
            resp = _client().post("/plan", json={"message": "杭州2天"})
            assert resp.status_code == 502
            body = resp.json()
            assert body["status"] == "error"
            # 内部异常细节不得泄漏
            assert "internal-detail" not in body["message"]

    def test_plan_message_validated(self):
        with patch("src.agents.travel_assistant.TravelAssistant"):
            resp = _client().post("/plan", json={"message": ""})
            assert resp.status_code == 422


class TestLlmConfigEndpoint:
    """多厂商 LLM 配置展示端点（密钥脱敏）。"""

    def test_default_config_masked(self, mock_env_vars):
        resp = _client().get("/config/llm")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        data = body["data"]
        assert data["provider"] == "zhipuai"
        assert data["model"] == "glm-5.1"
        assert "test_api_key" not in data["api_key"]  # 密钥不回显
        assert "zhipuai" in data["presets"]
        assert all("api_key" not in p for p in data["presets"].values())  # 预设无密钥

    def test_switched_provider(self, monkeypatch, mock_env_vars):
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        get_settings.cache_clear()
        try:
            resp = _client().get("/config/llm")
            data = resp.json()["data"]
            assert data["provider"] == "deepseek"
            assert data["model"] == "deepseek-chat"
        finally:
            get_settings.cache_clear()


class TestWebFrontend:
    """全新 Web 前端静态托管。"""

    def test_web_index_served(self):
        resp = _client().get("/web/")
        assert resp.status_code == 200
        assert "智能旅行助手" in resp.text
        assert "model-badge" in resp.text  # 多厂商模型展示已集成

    def test_root_json_contract_unchanged(self):
        """非浏览器请求（健康检查/压测）仍返回 JSON。"""
        resp = _client().get("/")
        body = resp.json()
        assert resp.status_code == 200
        assert body["status"] == "running"
        assert body["web"] == "/web/"

    def test_root_redirects_browsers_to_web(self):
        resp = _client().get(
            "/",
            headers={"Accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert resp.headers["location"] == "/web/"
