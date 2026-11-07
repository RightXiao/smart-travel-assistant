"""全新 Web 前端（静态 SPA）托管测试。

前端以零构建静态文件形式挂载在 ``/web``（``web/static`` 目录），由
FastAPI ``StaticFiles(html=True)`` 直接托管；根端点 ``/`` 契约保持不变。
"""
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
    """启用 API 鉴权（与 test_api.py 中语义一致）。"""
    monkeypatch.setenv("API_AUTH_TOKEN", "secret-token")
    get_settings.cache_clear()
    yield "secret-token"
    get_settings.cache_clear()


class TestWebStatic:
    """静态前端托管。"""

    def test_index_page(self):
        """/web/ 返回入口 HTML，包含品牌与挂载点。"""
        resp = _client().get("/web/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "智能旅行助手" in resp.text
        assert 'id="view"' in resp.text

    def test_index_page_without_trailing_slash(self):
        """/web（无斜杠）同样可达（StaticFiles html=True 行为）。"""
        resp = _client().get("/web")
        assert resp.status_code in (200, 307)

    def test_static_assets(self):
        """CSS / JS 静态资源可访问且类型正确。"""
        client = _client()
        css = client.get("/web/css/app.css")
        assert css.status_code == 200
        assert "text/css" in css.headers["content-type"]
        assert "--c-primary" in css.text

        js_api = client.get("/web/js/api.js")
        assert js_api.status_code == 200
        assert "TAApi" in js_api.text

        js_app = client.get("/web/js/app.js")
        assert js_app.status_code == 200
        assert "renderResult" in js_app.text

        js_mock = client.get("/web/js/mock.js")
        assert js_mock.status_code == 200

    def test_unknown_asset_404(self):
        """不存在的静态资源返回 404，不影响其他路由。"""
        resp = _client().get("/web/not-exist.js")
        assert resp.status_code == 404

    def test_root_contract_unchanged(self):
        """挂载前端后，根端点（非浏览器请求）仍返回 API 信息 JSON。"""
        from src import __version__

        resp = _client().get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["version"] == __version__
        assert body["web"] == "/web/"
        assert "name" in body

    def test_root_redirects_browsers_to_web(self):
        """浏览器访问根路径（Accept: text/html）自动跳转到 /web/，避免只看到 JSON。"""
        resp = _client().get(
            "/",
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"},
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert resp.headers["location"] == "/web/"

    def test_static_page_public_when_auth_enabled(self, auth_enabled):
        """开启 API 鉴权后静态页面仍公开（页面内 API 调用才校验 Token）。"""
        client = _client()
        page = client.get("/web/")
        assert page.status_code == 200
        api_resp = client.get("/spots/北京")
        assert api_resp.status_code == 401
