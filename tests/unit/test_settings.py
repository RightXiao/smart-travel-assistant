import pytest

from src.config import settings as settings_module


class TestSettings:
    """配置懒加载测试（覆盖 P1 修复点：导入时不崩、缺 key 时 require 报错）。"""

    def test_get_settings_lazy(self, mock_env_vars):
        s = settings_module.get_settings()
        assert s.AMAP_API_KEY == "test_amap_key"
        assert s.ZHIPUAI_MODEL == "glm-5.1"

    def test_get_settings_cached(self, mock_env_vars):
        a = settings_module.get_settings()
        b = settings_module.get_settings()
        assert a is b

    def test_require_keys_ok(self, mock_env_vars):
        settings_module.get_settings.cache_clear()
        # 配置了两个 key，不抛异常
        settings_module.require_api_keys()

    def test_require_keys_missing(self, monkeypatch):
        monkeypatch.setenv("ZHIPUAI_API_KEY", "")
        monkeypatch.setenv("AMAP_API_KEY", "")
        settings_module.get_settings.cache_clear()
        with pytest.raises(RuntimeError) as exc:
            settings_module.require_api_keys()
        assert "ZHIPUAI_API_KEY" in str(exc.value)
        assert "AMAP_API_KEY" in str(exc.value)

    def test_backward_compat_settings_attr(self, mock_env_vars):
        """旧的 ``from src.config.settings import settings`` 仍可用。"""
        s = settings_module.settings  # 触发模块级 __getattr__
        assert s is settings_module.get_settings()
