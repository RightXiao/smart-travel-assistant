import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_env_vars(monkeypatch):
    """模拟环境变量。"""
    monkeypatch.setenv("ZHIPUAI_API_KEY", "test_api_key")
    monkeypatch.setenv("AMAP_API_KEY", "test_amap_key")
    monkeypatch.setenv("APP_NAME", "测试旅行助手")
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture
def mock_requests_get():
    """模拟 requests.get 调用。"""
    with patch("requests.get") as mock_get:
        yield mock_get
