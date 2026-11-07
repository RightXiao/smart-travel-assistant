from unittest.mock import patch

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

    def test_runtime_defaults(self, mock_env_vars):
        """运行时配置默认值（鉴权默认关闭、Agent 参数与历史行为一致）。"""
        s = settings_module.get_settings()
        assert s.API_AUTH_TOKEN == ""  # 默认不启用鉴权
        assert s.AGENT_TEMPERATURE == 0.7
        assert s.AGENT_MAX_TOKENS == 4096
        assert s.AGENT_RECURSION_LIMIT >= 25  # 不低于 LangGraph 默认
        assert s.LLM_TIMEOUT > 0
        assert s.CACHE_MAX_SIZE > 0
        assert s.MEMORY_DIR == "memory"
        assert s.LOG_LEVEL == "INFO"


class TestResolveLlmConfig:
    """多厂商 LLM 配置解析（LLM_* 优先 + ZHIPUAI_* 向后兼容）。"""

    def test_default_zhipuai(self, mock_env_vars):
        from src.config.settings import resolve_llm_config

        cfg = resolve_llm_config()
        assert cfg["provider"] == "zhipuai"
        assert cfg["model"] == "glm-5.1"
        assert cfg["base_url"] == "https://open.bigmodel.cn/api/paas/v4/"
        assert cfg["api_key"] == "test_api_key"  # ZHIPUAI_API_KEY 回退生效

    def test_llm_fields_override(self, monkeypatch, mock_env_vars):
        monkeypatch.setenv("LLM_MODEL", "glm-4-air")
        monkeypatch.setenv("LLM_BASE_URL", "https://mirror.example.com/v1")
        monkeypatch.setenv("LLM_API_KEY", "sk-override")
        from src.config.settings import get_settings, resolve_llm_config

        get_settings.cache_clear()
        try:
            cfg = resolve_llm_config()
            assert cfg["model"] == "glm-4-air"
            assert cfg["base_url"] == "https://mirror.example.com/v1"
            assert cfg["api_key"] == "sk-override"
        finally:
            get_settings.cache_clear()

    def test_provider_switch_ignores_zhipuai_model(self, monkeypatch, mock_env_vars):
        """切换厂商后不继承 ZHIPUAI_MODEL（模型名不通用），用厂商预设默认。"""
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        from src.config.settings import get_settings, resolve_llm_config

        get_settings.cache_clear()
        try:
            cfg = resolve_llm_config()
            assert cfg["provider"] == "deepseek"
            assert cfg["model"] == "deepseek-chat"
            assert cfg["base_url"] == "https://api.deepseek.com/v1"
        finally:
            get_settings.cache_clear()

    def test_unknown_provider_raises(self, monkeypatch, mock_env_vars):
        monkeypatch.setenv("LLM_PROVIDER", "palm")
        from src.config.settings import get_settings, resolve_llm_config

        get_settings.cache_clear()
        try:
            with pytest.raises(ValueError) as exc:
                resolve_llm_config()
            assert "LLM_PROVIDER" in str(exc.value)
        finally:
            get_settings.cache_clear()

    def test_custom_requires_base_url(self, monkeypatch, mock_env_vars):
        monkeypatch.setenv("LLM_PROVIDER", "custom")
        from src.config.settings import get_settings, resolve_llm_config

        get_settings.cache_clear()
        try:
            with pytest.raises(ValueError) as exc:
                resolve_llm_config()
            assert "LLM_BASE_URL" in str(exc.value)
            monkeypatch.setenv("LLM_BASE_URL", "http://10.0.0.5:8000/v1")
            get_settings.cache_clear()
            cfg = resolve_llm_config()
            assert cfg["base_url"] == "http://10.0.0.5:8000/v1"
        finally:
            get_settings.cache_clear()

    def test_require_keys_with_generic_llm_key(self, monkeypatch):
        """仅配置 LLM_API_KEY（不配 ZHIPUAI_API_KEY）即可通过校验。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-generic")
        monkeypatch.setenv("AMAP_API_KEY", "amap-key")
        monkeypatch.setenv("ZHIPUAI_API_KEY", "")
        from src.config.settings import get_settings, require_api_keys

        get_settings.cache_clear()
        try:
            require_api_keys()  # 不抛异常
        finally:
            get_settings.cache_clear()

    def test_ollama_keyless_allowed(self, monkeypatch):
        """ollama 本地服务可无密钥运行。"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("LLM_API_KEY", "")
        monkeypatch.setenv("ZHIPUAI_API_KEY", "")
        monkeypatch.setenv("AMAP_API_KEY", "amap-key")
        from src.config.settings import get_settings, require_api_keys

        get_settings.cache_clear()
        try:
            require_api_keys()
        finally:
            get_settings.cache_clear()


class TestBuildChatModel:
    """LLM 工厂：参数来自 resolve_llm_config + Settings。"""

    def test_uses_resolved_provider_config(self, monkeypatch, mock_env_vars):
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")
        from unittest.mock import patch

        from src.config import llm as llm_module
        from src.config.settings import get_settings

        get_settings.cache_clear()
        try:
            with patch.object(llm_module, "ChatOpenAI") as mock_ctor:
                llm_module.build_chat_model(temperature=0.2)
                kwargs = mock_ctor.call_args.kwargs
                assert kwargs["model"] == "deepseek-chat"
                assert kwargs["base_url"] == "https://api.deepseek.com/v1"
                assert kwargs["temperature"] == 0.2
                assert kwargs["max_tokens"] == get_settings().AGENT_MAX_TOKENS
        finally:
            get_settings.cache_clear()

    def test_empty_key_gets_placeholder(self, monkeypatch, mock_env_vars):
        """无密钥厂商（ollama）用 EMPTY 占位，客户端构造不报错。"""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("LLM_API_KEY", "")
        monkeypatch.setenv("ZHIPUAI_API_KEY", "")
        from src.config import llm as llm_module
        from src.config.settings import get_settings

        get_settings.cache_clear()
        try:
            with patch.object(llm_module, "ChatOpenAI") as mock_ctor:
                llm_module.build_chat_model()
                assert mock_ctor.call_args.kwargs["api_key"] == "EMPTY"
        finally:
            get_settings.cache_clear()
