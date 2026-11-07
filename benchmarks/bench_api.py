"""轻量压测基准：对运行中的 API 做并发请求，输出 RPS 与延迟分位数。

用途：在决定是否需要进一步异步化/扩容前，量化当前 API 的吞吐与延迟基线。
仅用标准库实现，无额外依赖；默认探测根端点（无外部依赖、无副作用），
也可指定任意路径（如 ``/weather/北京``，注意会消耗真实配额）。

用法::

    # 1. 启动服务
    uvicorn src.api.main:app --host 127.0.0.1 --port 8000

    # 2. 压测（20 并发 × 共 200 请求）
    python benchmarks/bench_api.py --concurrency 20 --requests 200

    # 指定路径与鉴权
    python benchmarks/bench_api.py --path /spots/北京 --token $API_AUTH_TOKEN
"""
from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def _percentile(sorted_values: list, pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(int(len(sorted_values) * pct / 100), len(sorted_values) - 1)
    return sorted_values[idx]


def _worker(
    url: str,
    headers: dict,
    count: int,
    latencies: list,
    statuses: Counter,
    errors: list,
    lock: threading.Lock,
) -> None:
    for _ in range(count):
        started = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:  # 网络/超时
            with lock:
                errors.append(str(e))
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000
        with lock:
            latencies.append(elapsed_ms)
            statuses[status] += 1


def run_benchmark(url: str, concurrency: int, total: int, headers: dict) -> dict:
    """执行压测，返回 ``{"rps", "latencies_ms", "p50", "p95", "p99", "statuses", "errors"}``。"""
    per_worker = max(total // concurrency, 1)
    latencies: list = []
    statuses: Counter = Counter()
    errors: list = []
    lock = threading.Lock()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                _worker, url, headers, per_worker, latencies, statuses, errors, lock
            )
            for _ in range(concurrency)
        ]
        for f in futures:
            f.result()
    wall = time.perf_counter() - started

    latencies.sort()
    actual_total = len(latencies) + len(errors)
    return {
        "url": url,
        "concurrency": concurrency,
        "requests": actual_total,
        "wall_seconds": round(wall, 2),
        "rps": round(actual_total / wall, 1) if wall > 0 else 0.0,
        "p50_ms": round(_percentile(latencies, 50), 1),
        "p95_ms": round(_percentile(latencies, 95), 1),
        "p99_ms": round(_percentile(latencies, 99), 1),
        "statuses": dict(statuses),
        "errors": errors[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="旅行助手 API 轻量压测")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="服务基地址")
    parser.add_argument("--path", default="/", help="压测路径（默认根端点）")
    parser.add_argument("--concurrency", type=int, default=20, help="并发线程数")
    parser.add_argument("--requests", type=int, default=200, help="总请求数")
    parser.add_argument("--token", default="", help="Bearer Token（服务启用鉴权时传）")
    args = parser.parse_args()

    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    report = run_benchmark(
        f"{args.url.rstrip('/')}{args.path}", args.concurrency, args.requests, headers
    )
    print("\n📈 压测报告")
    print(f"  目标: {report['url']}")
    print(
        f"  并发: {report['concurrency']}  请求数: {report['requests']}  "
        f"耗时: {report['wall_seconds']}s"
    )
    print(f"  吞吐: {report['rps']} req/s")
    print(
        f"  延迟: p50={report['p50_ms']}ms  p95={report['p95_ms']}ms  "
        f"p99={report['p99_ms']}ms"
    )
    print(f"  状态码: {report['statuses']}")
    if report["errors"]:
        print(f"  错误示例: {report['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
