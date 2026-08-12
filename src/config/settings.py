from functools import lru_cache
from typing import Optional

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

    # 网络 / 缓存调优
    HTTP_TIMEOUT: int = 10          # 高德 API 请求超时（秒）
    HTTP_MAX_RETRIES: int = 3       # 失败重试次数
    CACHE_TTL: int = 1800           # POI / 天气等结果缓存有效期（秒）

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例 Settings（懒加载，可被测试覆写）。"""
    return Settings()


def require_api_keys() -> None:
    """校验必需的 API Key 是否已配置，缺失时抛出 RuntimeError。

    供需要真实调用外部服务的入口（Agent / API / CLI / Web）显式调用，
    而不是在模块导入时即崩溃。
    """
    missing = []
    if not get_settings().ZHIPUAI_API_KEY:
        missing.append("ZHIPUAI_API_KEY")
    if not get_settings().AMAP_API_KEY:
        missing.append("AMAP_API_KEY")
    if missing:
        raise RuntimeError(
            "缺少必需的 API Key：" + "、".join(missing)
            + "。请在项目根目录的 .env 文件中配置（参考 .env.example）。"
        )


# 向后兼容：保留 ``settings`` 名称，旧代码 ``from src.config.settings import settings`` 仍可用，
# 但更推荐使用 ``get_settings()``。
def __getattr__(name: str):
    if name == "settings":
        return get_settings()
    raise AttributeError(name)
