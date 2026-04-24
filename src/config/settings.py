import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    ZHIPUAI_API_KEY: str = os.getenv("ZHIPUAI_API_KEY", "")
    ZHIPUAI_MODEL: str = os.getenv("ZHIPUAI_MODEL", "glm-5.1")
    
    AMAP_API_KEY: str = os.getenv("AMAP_API_KEY", "")
    
    APP_NAME: str = os.getenv("APP_NAME", "智能旅行助手")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"


settings = Settings()
