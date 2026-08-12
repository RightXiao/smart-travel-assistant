"""共享 pytest fixtures。

工具层已从直接 ``requests.get`` 改为统一走 :func:`src.utils.http.cached_json_get`，
因此单测应 mock 各工具模块中绑定的 ``cached_json_get`` 引用
（这些模块在顶层 ``from src.utils.http import cached_json_get``，持有各自引用）。
"""
import pytest


@pytest.fixture
def mock_env_vars(monkeypatch):
    """模拟环境变量，并清空 settings 缓存使其重新读取。"""
    monkeypatch.setenv("ZHIPUAI_API_KEY", "test_api_key")
    monkeypatch.setenv("AMAP_API_KEY", "test_amap_key")
    monkeypatch.setenv("APP_NAME", "测试旅行助手")
    monkeypatch.setenv("DEBUG", "true")

    from src.config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_http(monkeypatch):
    """统一 mock 高德 HTTP 调用。

    由于各工具模块顶层 ``from src.utils.http import cached_json_get``，
    这里对四个模块的绑定逐一打补丁。

    返回一个 ``setter``：``mock_http({...})`` 设置下一次返回值。
    默认返回 ``{"status": "1"}``。
    """
    from src.utils import http
    http.clear_cache()

    holder = {"value": {"status": "1"}}

    def fake_get(url, params, cache_key=None, timeout=None):
        return holder["value"]

    import src.tools.amap.geocode as geocode_mod
    import src.tools.amap.poi as poi_mod
    import src.tools.amap.route as route_mod
    import src.tools.amap.weather as weather_mod
    monkeypatch.setattr(weather_mod, "cached_json_get", fake_get)
    monkeypatch.setattr(poi_mod, "cached_json_get", fake_get)
    monkeypatch.setattr(route_mod, "cached_json_get", fake_get)
    monkeypatch.setattr(geocode_mod, "cached_json_get", fake_get)

    def set_response(value):
        holder["value"] = value

    yield set_response

    http.clear_cache()
