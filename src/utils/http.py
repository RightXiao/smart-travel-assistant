"""共享的 HTTP 客户端与简易 TTL 缓存工具。

集中管理 ``requests.Session``（带连接池 + 自动重试）与轻量内存缓存，
避免每个工具各自 ``requests.get`` 时：
- 重复创建连接、无重试；
- 同一城市 / 关键词短时间内反复请求高德 API 浪费配额。
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.settings import get_settings
from src.utils.logger import logger

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_session: requests.Session | None = None
_session_lock = threading.Lock()


def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=get_settings().HTTP_MAX_RETRIES,
        backoff_factor=0.5,  # 0.5, 1, 2 ... 秒指数退避
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def get_session() -> requests.Session:
    """返回进程级共享 ``requests.Session``（惰性创建，双重检查加锁）。"""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = _build_session()
    return _session


# ---------------------------------------------------------------------------
# Cached GET helper
# ---------------------------------------------------------------------------


class TTLCache:
    """进程内 TTL 缓存：按 ``key`` 存 (value, expire_at)。

    - 线程安全：所有读写都在锁内（FastAPI 同步端点运行在线程池中）。
    - 容量上限：超过 ``max_size`` 时按插入顺序 FIFO 淘汰，防止长期运行内存无界增长。
    """

    def __init__(self, max_size: int | None = None) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._max_size = (
            max_size if max_size is not None else get_settings().CACHE_MAX_SIZE
        )

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else get_settings().CACHE_TTL
        with self._lock:
            if key not in self._store and len(self._store) >= self._max_size:
                # dict 保持插入序，弹出最早的条目（FIFO）
                oldest = next(iter(self._store))
                self._store.pop(oldest, None)
            self._store[key] = (value, time.time() + ttl)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_cache = TTLCache()


def cached_json_get(
    url: str,
    params: dict[str, Any],
    *,
    cache_key: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any] | None:
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


# ---------------------------------------------------------------------------
# 异步 HTTP（httpx.AsyncClient，供 async 端点使用，避免阻塞事件循环）
# ---------------------------------------------------------------------------

_async_client: httpx.AsyncClient | None = None
_async_client_lock = threading.Lock()


def _get_async_client() -> httpx.AsyncClient:
    """进程级共享 ``httpx.AsyncClient``（惰性创建，双重检查加锁）。"""
    global _async_client
    if _async_client is None:
        with _async_client_lock:
            if _async_client is None:
                _async_client = httpx.AsyncClient(
                    timeout=float(get_settings().HTTP_TIMEOUT),
                    limits=httpx.Limits(
                        max_connections=20, max_keepalive_connections=10
                    ),
                )
    return _async_client


async def aclose_async_client() -> None:
    """关闭共享异步客户端（应用 shutdown 时调用）。"""
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


async def acached_json_get(
    url: str,
    params: dict[str, Any],
    *,
    cache_key: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any] | None:
    """:func:`cached_json_get` 的异步版本（缓存与负缓存语义一致）。"""
    if cache_key is not None:
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.debug("缓存命中：%s", cache_key)
            return cached

    request_timeout = timeout if timeout is not None else get_settings().HTTP_TIMEOUT
    try:
        resp = await _get_async_client().get(
            url, params=params, timeout=request_timeout
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.error("异步 HTTP 请求失败 %s: %s", url, e)
        return None
    except ValueError as e:  # JSON 解析失败
        logger.error("响应 JSON 解析失败 %s: %s", url, e)
        return None

    # 与同步版一致：仅缓存成功响应
    if cache_key is not None and isinstance(data, dict) and data.get("status") == "1":
        _cache.set(cache_key, data)
    return data
