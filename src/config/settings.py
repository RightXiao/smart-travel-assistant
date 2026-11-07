from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置设置。

    使用 ``lru_cache`` 包装的 :func:`get_settings` 进行懒加载，
    避免在导入阶段（未配置 ``.env`` 时）即触发校验失败，
    也便于测试时通过 ``get_settings.cache_clear()`` 刷新配置。
    """

    ZHIPUAI_API_KEY: str = ""
    ZHIPUAI_MODEL: str = "glm-5.1"
    ZHIPUAI_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4/"
    AMAP_API_KEY: str = ""
    APP_NAME: str = "智能旅行助手"
    DEBUG: bool = False

    # 多厂商 LLM 接入（OpenAI 兼容端点）。
    # 优先级：LLM_* > ZHIPUAI_*（zhipuai 专属回退）> 厂商预设默认值。
    # 切换厂商时建议显式设置 LLM_MODEL（各厂商模型名不通用）。
    LLM_PROVIDER: str = (
        "zhipuai"  # zhipuai | deepseek | qwen | moonshot | openai | ollama | custom
    )
    LLM_API_KEY: str = ""  # 未设置时回退 ZHIPUAI_API_KEY；ollama 本地服务可不设
    LLM_MODEL: str = ""  # 未设置时按厂商取默认模型
    LLM_BASE_URL: str = ""  # 未设置时取厂商预设；custom 必填（vLLM / LM Studio 等）
    EMBEDDING_MODEL: str = ""  # 未设置时回退 ZHIPUAI_EMBEDDING_MODEL

    # 网络 / 缓存调优
    HTTP_TIMEOUT: int = 10  # 高德 API 请求超时（秒）
    HTTP_MAX_RETRIES: int = 3  # 失败重试次数
    CACHE_TTL: int = 1800  # POI / 天气等结果缓存有效期（秒）
    CACHE_MAX_SIZE: int = 512  # 进程内缓存最大条目数（FIFO 淘汰，防无界增长）

    # LLM / Agent 调优
    AGENT_TEMPERATURE: float = 0.7  # 生成多样性
    AGENT_MAX_TOKENS: int = 4096  # 单次回复最大 token
    AGENT_RECURSION_LIMIT: int = 40  # ReAct 循环步数上限（默认 25 对多工具攻略偏紧）
    LLM_TIMEOUT: int = 120  # LLM 请求超时（秒）
    LLM_MAX_RETRIES: int = 2  # LLM 请求失败重试次数

    # 可观测性 / 运行时
    LOG_LEVEL: str = "INFO"  # 日志级别（DEBUG=true 时强制 DEBUG）
    MEMORY_DIR: str = "memory"  # 会话记忆存储目录
    MEMORY_BACKEND: str = "file"  # 会话记忆后端：file | sqlite

    # 上下文窗口
    AGENT_HISTORY_LIMIT: int = 8  # 直传 LLM 的历史消息条数
    AGENT_HISTORY_CONTENT_MAX: int = 500  # 单条历史内容截断长度

    # 行程规划（Plan-and-Execute）
    PLAN_VERIFY_RETRIES: int = 1  # 结构化草稿未通过校验时的自纠重试次数

    # 向量语义记忆（依赖 embeddings API 调用，默认关闭）
    SEMANTIC_MEMORY_ENABLED: bool = False
    SEMANTIC_MEMORY_TOP_K: int = 3  # 每轮召回的相关记忆条数
    SEMANTIC_MEMORY_MAX_ENTRIES: int = 500  # 记忆条目上限（FIFO 淘汰）
    ZHIPUAI_EMBEDDING_MODEL: str = "embedding-2"

    # API 访问控制：为空时不启用鉴权（本地开发）；
    # 设置后所有端点要求 Authorization: Bearer <token>
    API_AUTH_TOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例 Settings（懒加载，可被测试覆写）。"""
    return Settings()


# 各厂商 OpenAI 兼容端点预设（均无密钥信息，可安全对外展示）。
LLM_PRESETS: dict = {
    "zhipuai": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_model": "glm-5.1",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
    },
    "openai": {"base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    "ollama": {"base_url": "http://localhost:11434/v1", "default_model": "qwen2.5:7b"},
    "custom": {"base_url": "", "default_model": ""},  # 自建 OpenAI 兼容服务（vLLM 等）
}

# 该厂商可无密钥运行（本地推理服务）
KEYLESS_PROVIDERS = {"ollama"}


def resolve_llm_config() -> dict:
    """解析生效的 LLM 接入配置（厂商/密钥/模型/端点）。

    优先级：
    - provider：``LLM_PROVIDER``（默认 zhipuai）；
    - api_key：``LLM_API_KEY`` > ``ZHIPUAI_API_KEY``（向后兼容）；
    - model：``LLM_MODEL`` > （zhipuai 时 ``ZHIPUAI_MODEL``）> 厂商预设默认；
    - base_url：``LLM_BASE_URL`` > 厂商预设。

    Returns:
        ``{"provider", "api_key", "model", "base_url"}``。

    Raises:
        ValueError: 未知厂商；或 custom 未配置 ``LLM_BASE_URL``。
    """
    s = get_settings()
    provider = (s.LLM_PROVIDER or "zhipuai").strip().lower()
    if provider not in LLM_PRESETS:
        raise ValueError(f"未知的 LLM_PROVIDER：{provider}。可选值：{'、'.join(LLM_PRESETS)}")
    preset = LLM_PRESETS[provider]

    api_key = s.LLM_API_KEY or s.ZHIPUAI_API_KEY
    if provider == "zhipuai":
        model = s.LLM_MODEL or s.ZHIPUAI_MODEL or preset["default_model"]
    else:
        # ZHIPUAI_MODEL 是智谱专属配置，切换厂商后不应继承（模型名不通用）
        model = s.LLM_MODEL or preset["default_model"]
    base_url = s.LLM_BASE_URL or preset["base_url"]

    if provider == "custom" and not base_url:
        raise ValueError("LLM_PROVIDER=custom 时必须设置 LLM_BASE_URL（OpenAI 兼容端点）")

    return {
        "provider": provider,
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
    }


def resolve_embedding_model() -> str:
    """解析生效的 embeddings 模型名（``EMBEDDING_MODEL`` > ``ZHIPUAI_EMBEDDING_MODEL``）。"""
    s = get_settings()
    return s.EMBEDDING_MODEL or s.ZHIPUAI_EMBEDDING_MODEL


def require_api_keys() -> None:
    """校验 LLM 与高德地图的必需配置，缺失时抛 RuntimeError。

    供需要真实调用外部服务的入口（Agent / API / CLI / Web）显式调用，
    而不是在模块导入时即崩溃。ollama 等本地推理服务可无密钥运行。
    """
    s = get_settings()
    missing = []
    llm_cfg = resolve_llm_config()  # 顺带校验 provider / custom base_url 合法性
    if (
        not llm_cfg["api_key"]
        and s.LLM_PROVIDER.strip().lower() not in KEYLESS_PROVIDERS
    ):
        missing.append("LLM_API_KEY（或 ZHIPUAI_API_KEY）")
    if not s.AMAP_API_KEY:
        missing.append("AMAP_API_KEY")
    if missing:
        raise RuntimeError(
            "缺少必需的 API Key："
            + "、".join(missing)
            + "。请在项目根目录的 .env 文件中配置（参考 .env.example）。"
        )


# 向后兼容：保留 ``settings`` 名称，旧代码 ``from src.config.settings import settings`` 仍可用，
# 但更推荐使用 ``get_settings()``。
def __getattr__(name: str):
    if name == "settings":
        return get_settings()
    raise AttributeError(name)
