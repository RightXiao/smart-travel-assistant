"""FastAPI 应用入口 — 使用 uvicorn src.api.main:app 启动"""
from src.api import app

# app 已在 src/api/__init__.py 中定义，这里重新导出方便 uvicorn 发现
__all__ = ["app"]
