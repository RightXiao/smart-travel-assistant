"""共享的 HTTP 客户端与简易 TTL 缓存工具。

集中管理 ``requests.Session``（带连接池 + 自动重试）与轻量内存缓存，
避免每个工具各自 ``requests.get`` 时：
- 重复创建连接、无重试；
- 同一城市 / 关键词短时间内反复请求高德 API 浪费配额。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.settings import get_settings
from src.utils.logger import logger

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_session: Optional[requests.Session] = None


def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=get_settings().HTTP_MAX_RETRIES,
        backoff_factor=0.5,                       # 0.5, 1, 2 ... 秒指数退避
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def get_session() -> requests.Session:
    """返回进程级共享 ``requests.Session``（惰性创建）。"""
    global _session
    if _session is None:
        _session = _build_session()
    return _session


# ---------------------------------------------------------------------------
# Cached GET helper
# ---------------------------------------------------------------------------

class TTLCache:
    """极简进程内 TTL 缓存。按 ``key`` 存 (value, expire_at)。"""

    def __init__(self) -> None:
        self._store: Dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        if time.time() > expire_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else get_settings().CACHE_TTL
        self._store[key] = (value, time.time() + ttl)

    def clear(self) -> None:
        self._store.clear()


_cache = TTLCache()


def cached_json_get(url: str, params: Dict[str, Any], *, cache_key: Optional[str] = None,
                    timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """带缓存 + 重试的 GET，返回 JSON dict（失败返回 None）。

    Args:
        url: 请求地址。
        params: 查询参数。
        cache_key: 缓存键；为 None 时不缓存。建议用 ``f"{url}:{稳定参数}"``。
        timeout: 覆盖默认超时。
    """
    if cache_key is not None:
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.debug("缓存命中：%s", cache_key)
            return cached

    timeout = timeout if timeout is not None else get_settings().HTTP_TIMEOUT
    try:
        resp = get_session().get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("HTTP 请求失败 %s: %s", url, e)
        return None
    except ValueError as e:  # JSON 解析失败
        logger.error("响应 JSON 解析失败 %s: %s", url, e)
        return None

    # 仅缓存「成功」响应：高德约定 status=="1" 表示成功。错误体（status=="0"）
    # 若也缓存，会导致 API 短暂故障被缓存整个 TTL，恢复后仍持续返回失败。
    if cache_key is not None and isinstance(data, dict) and data.get("status") == "1":
        _cache.set(cache_key, data)
    return data


def clear_cache() -> None:
    """清空缓存（供测试或手动刷新使用）。"""
    _cache.clear()
