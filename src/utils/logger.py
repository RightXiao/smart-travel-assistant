import logging
import sys
from typing import Optional

from src.config.settings import get_settings


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """设置日志记录器。

    通过 ``if not logger.handlers`` 守卫，避免在多个模块 import 时
    重复添加 handler 导致同一行日志输出多次。

    Args:
        name: 日志记录器名称。
        level: 日志级别。
        log_file: 日志文件路径（可选）。

    Returns:
        配置好的日志记录器。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 已有 handler 则不再重复添加（防止多模块 import 后重复输出）
    if not logger.handlers:
        fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(console_handler)

        if log_file:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(fmt))
            logger.addHandler(file_handler)

    # 避免日志向 root logger 冒泡造成二次输出
    logger.propagate = False
    return logger


# 全局日志记录器：根据 Settings.DEBUG 决定级别
logger = setup_logger(
    "travel_agent",
    level=logging.DEBUG if get_settings().DEBUG else logging.INFO,
)
