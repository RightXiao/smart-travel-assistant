"""异步 HTTP 层与工具 a- 变体测试（httpx.MockTransport，无真实网络）。"""
from unittest.mock import patch

import httpx
import pytest

from src.utils.http import acached_json_get, clear_cache


def _client_with(handler):
    """构造挂了 MockTransport 的假共享异步客户端。"""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _reset():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.asyncio
class TestACachedJsonGet:
    async def test_success_and_cache(self, mock_env_vars):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"status": "1", "data": "ok"})

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            first = await acached_json_get("http://x", {"a": 1}, cache_key="k1")
            second = await acached_json_get("http://x", {"a": 1}, cache_key="k1")
        assert first == {"status": "1", "data": "ok"}
        assert second == first
        assert calls["n"] == 1  # 第二次命中缓存

    async def test_error_body_not_cached(self, mock_env_vars):
        """负缓存语义：status!=1 不缓存，恢复后立即可重试。"""
        responses = [
            httpx.Response(200, json={"status": "0", "info": "临时错误"}),
            httpx.Response(200, json={"status": "1", "data": "ok"}),
        ]

        def handler(request):
            return responses.pop(0)

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            first = await acached_json_get("http://x", {}, cache_key="k2")
            second = await acached_json_get("http://x", {}, cache_key="k2")
        assert first["status"] == "0"
        assert second["status"] == "1"

    async def test_http_error_returns_none(self, mock_env_vars):
        def handler(request):
            return httpx.Response(500)

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            result = await acached_json_get("http://x", {}, cache_key="k3")
        assert result is None

    async def test_no_cache_key_bypasses_cache(self, mock_env_vars):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"status": "1"})

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            await acached_json_get("http://x", {}, cache_key=None)
            await acached_json_get("http://x", {}, cache_key=None)
        assert calls["n"] == 2


@pytest.mark.asyncio
class TestAsyncTools:
    async def test_aget_weather(self, mock_env_vars):
        from src.tools.amap.weather import WeatherTool

        def handler(request):
            assert "weatherInfo" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "lives": [{"city": "杭州", "weather": "晴", "temperature": "25"}],
                },
            )

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            data = await WeatherTool.aget_weather("杭州")
        assert data["lives"][0]["city"] == "杭州"

    async def test_asearch_poi_with_business_fields(self, mock_env_vars):
        from src.tools.amap.poi import POITool

        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [{"name": "灵隐寺", "location": "120.1,30.2"}],
                },
            )

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            data = await POITool.asearch_poi(
                keywords="景点", city="杭州", types="110000", with_business=True
            )
        assert data["pois"][0]["name"] == "灵隐寺"
        assert "show_fields=biz_ext" in captured["url"]

    async def test_asearch_hotel_by_budget_filters(self, mock_env_vars):
        from src.tools.amap.poi import POITool

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [
                        {"name": "青旅", "biz_ext": {"cost": "150"}},
                        {"name": "五星", "biz_ext": {"cost": "1500"}},
                        {"name": "无价目", "biz_ext": {}},
                    ],
                },
            )

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            data = await POITool.asearch_hotel_by_budget("杭州", "经济型")
        names = [p["name"] for p in data["pois"]]
        # 经济型(<300)：命中的在前，无价目的兜底保留，超预算被过滤
        assert names == ["青旅", "无价目"]

    async def test_aget_driving_route_unresolvable(self, mock_env_vars):
        """地名无法定位（异步）应抛 RouteResolutionError。"""
        from src.tools.amap.route import RouteResolutionError, RouteTool

        def handler(request):
            return httpx.Response(200, json={"status": "0", "info": "INVALID_PARAMS"})

        with patch(
            "src.utils.http._get_async_client", return_value=_client_with(handler)
        ):
            with pytest.raises(RouteResolutionError) as exc:
                await RouteTool.aget_driving_route("不存在的地方", "故宫")
        assert "无法定位起点" in str(exc.value)
