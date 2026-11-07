# AGENTS.md

智能旅行助手：LangGraph ReAct Agent（GLM-5.1 + 高德地图 API），提供 FastAPI（`src/api`）、Streamlit（`web/`）、CLI（`src/cli`）三个入口。代码注释、日志与文档均为中文，请保持一致。

## 常用命令

```bash
.venv/bin/python -m pytest -q                                   # 全量测试
.venv/bin/python -m pytest -q --cov=src --cov-report=term       # 带覆盖率
.venv/bin/ruff check . && .venv/bin/black --check .             # lint / 格式（CI 门禁）
RUN_EVALS=1 .venv/bin/python -m pytest -m eval -q               # 离线评估（需真实 API Key，默认跳过）
PYTHONPATH=. .venv/bin/python -m evals.runner --judge           # 质量回归评估
PYTHONPATH=. .venv/bin/python benchmarks/bench_api.py           # 压测（需先启动 uvicorn）
```

- 测试**绝不**访问真实网络/LLM：高德调用 mock `cached_json_get`，LLM mock `TravelAssistant` 构造（见 `tests/conftest.py`）。
- dev 依赖在 `requirements-dev.txt` **锁定精确版本**（浮动版本曾导致 CI 漂移），勿改回范围版本。

## 架构边界（改代码前必读 `docs/architecture.md`）

- **分层**：`tools/amap`（高德封装，同步 + `a*` 异步成对出现，错误语义必须一致）→ `agents`（ReAct / `plan_trip`）→ `api`（端点）。`planner/` 是确定性引擎（排程/预算），**不允许引入 LLM 调用**。
- **所有高德请求**必须走 `src/utils/http.py` 的 `cached_json_get` / `acached_json_get`（TTL 缓存、仅缓存 `status=="1"`），禁止裸 `requests.get`。
- **工具输出**返回给 LLM 前必须过 `src/utils/sanitize.py` 的 `sanitize_tool_output`（防注入/密钥脱敏/限长）。
- **API 错误契约**：成功 200 `{status: "ok"}`；上游失败 502；地名无法定位 400（抛 `RouteResolutionError`）；校验失败 422。所有响应带 `X-Request-ID`。改契约需同步 README 端点表与 `tests/unit/test_api.py`。
- **结构化行程**（`POST /plan`）的核心不变量：景点名只能来自 POI 查询结果、`total_estimated_cost` 必须等于各日 + 住宿之和——由 `src/agents/verifier.py` 强制，勿绕过。
- **版本号**三处同步：`src/__init__.py` / `pyproject.toml` / `CHANGELOG.md`（语义化版本，每次改动更新 CHANGELOG）。

## 配置与兼容性

- 配置统一走 `src/config/settings.py`（pydantic-settings，`lru_cache` 懒加载）；新增配置需同步 `.env.example` 与 README 配置表。
- **Python 3.9 兼容**（CI 矩阵 3.9/3.11）：`X | None` 注解只允许出现在带 `from __future__ import annotations` 的文件中；否则用 `Optional`。ruff target 为 py39，会拦截。
- 路由工具的坐标约定：`"经度,纬度"` 含逗号即视为坐标，否则先地理编码。

## 测试约定（常见坑）

- 各工具模块顶层绑定了 `cached_json_get` 引用，mock 需逐模块 patch——`conftest.py` 的 `mock_http` fixture 当前覆盖 weather/poi/route/geocode 四个模块，**新增工具模块必须加入**。
- 异步工具测试用 `httpx.MockTransport` + patch `_get_async_client`（见 `tests/unit/test_async_tools.py`）；FastAPI 依赖解析先于 body 校验，422 类测试需先 patch `TravelAssistant`。
- 环境相关测试用 `mock_env_vars` fixture（内部做 `get_settings.cache_clear()`）；settings 是全局缓存单例，直接改 `.env` 不会生效。
