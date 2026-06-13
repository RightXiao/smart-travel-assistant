from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置设置。"""
    
    ZHIPUAI_API_KEY: str
    ZHIPUAI_MODEL: str = "glm-5.1"
    AMAP_API_KEY: str
    APP_NAME: str = "智能旅行助手"
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局单例
settings = Settings()
