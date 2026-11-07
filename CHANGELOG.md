# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.5.0] - 2026-11-07

### 🎨 全新 Web 前端（攻略定制主流程）

- **零构建静态 SPA**：新增 `web/static/`（原生 HTML/CSS/JS，无前端依赖与构建步骤），由 FastAPI 以 `StaticFiles(html=True)` 挂载在 `/web`，`uvicorn src.api.main:app` 启动即得完整界面；浏览器访问根路径 `/`（`Accept: text/html`）自动 307 跳转 `/web/`，非浏览器请求（curl/健康检查/压测）仍返回 200 JSON 契约不变，Streamlit 界面保留共存。
- **页面层级**（hash 路由）：`#/` 需求定制表单（目的地/日期天数/预算/同行人/节奏/兴趣偏好/补充说明，含校验与草稿持久化）→ `#/generating` 定制中（对齐真实管线的 6 阶段进度动画 + 计时）→ `#/result` 定制结果（行程头卡 / 偏好回显 / 预算进度与费用拆分 / 逐日卡片 / 美食住宿贴士 / 校验提示）→ `#/day/:n` 行程详情（单日时间线 + 多景点真实路线查询）。
- **状态设计完备**：表单校验错误、按钮/内联加载态与骨架屏、灵感速览空态、结果页无数据空态、400/401/422/502/超时/网络断开分级错误态（含 `X-Request-ID` 追踪展示）、SSE 流式与中断处理。
- **能力接线**：`POST /plan` 结构化定制、`GET /weather|/spots|/food` 灵感速览、`POST /route/multi-spot` 当日真实路线、`POST /chat/stream` 全局 AI 助手抽屉（工具进度 + token 流式渲染）；会话 ID 持久化以复用用户画像记忆；可选 `API_AUTH_TOKEN` 在页面「连接设置」配置。
- **演示模式**：`/web/?mock=1` 内置 mock 数据拦截（含错误触发词），无 API Key 亦可完整演示与验收全部页面状态。
- **模型接入可视化**：页头「当前模型」徽章（厂商 · 模型），连接设置弹层展示当前接入详情（厂商/模型/端点/脱敏 Key）与支持的厂商预设列表（当前厂商高亮），页脚署名随配置动态更新；配置接口不可用时静默降级。

### 🔌 多厂商模型接入

- **厂商预设表**：`LLM_PRESETS` 内置 zhipuai / deepseek / qwen / moonshot / openai / ollama / custom 七种 OpenAI 兼容端点预设；新增厂商只需加预设，无需改代码。
- **配置解析**（`resolve_llm_config`）：`LLM_*` > `ZHIPUAI_*`（智谱专属回退）> 厂商预设默认值；切换厂商不继承 `ZHIPUAI_MODEL`（模型名不通用）；`custom` 必填 `LLM_BASE_URL`（vLLM / LM Studio 等）；ollama 本地服务可无密钥运行（`KEYLESS_PROVIDERS`）。
- **统一工厂**：`src/config/llm.py` 的 `build_chat_model` / `build_embedding_client` 成为 LLM 客户端唯一入口，Agent / 评测 judge / 语义记忆 embeddings 三处全部接线；无密钥厂商以 `EMPTY` 占位。
- **`GET /config/llm`**：展示生效厂商 / 模型 / 端点（密钥脱敏）与全部厂商预设（无敏感信息），配置错误返回 500 + 明确原因。
- 文档同步：README 新增「多厂商模型接入」配置章节与切换示例；architecture.md 推理引擎小节更新为多厂商接入层说明。

### 🧪 测试

- 新增 21 个用例（240 → 261 passed）：provider 解析/回退/继承规则/未知厂商/custom 校验、ollama 免密钥、LLM 工厂参数与占位、`/config/llm` 契约（脱敏/预设）、`/web` 挂载、根端点浏览器跳转与 JSON 契约；Agent 测试 patch 目标统一迁移到 `build_chat_model`。

## [1.4.0] - 2026-11-07

### 🗓️ 结构化行程规划（Plan-and-Execute + Verifier）

- **结构化输出契约**：新增 `src/models/plan.py`——`TripRequestArgs`（参数抽取）与 `TravelPlan`/`DayPlan`（行程方案），经 `llm.with_structured_output` 强制 schema，不再信任自由文本。
- **Verifier 校验器**（`src/agents/verifier.py`）：**预算算术一致性**（各日合计 + 住宿 = 总估算，容忍 1 元舍入）、**景点名事实锚定**（行程景点必须出现在高德 POI 查询结果中，幻觉防护；景点池为空降级为告警）、**预算上限告警**。
- **确定性引擎**：`src/planner/itinerary.py` 逐日排程（复用最近邻贪心排序 + 连续切块 + haversine 距离估算）；`src/planner/budget.py` 预算拆分（餐饮/交通确定性下限，作为生成 prompt 的事实锚点）；地理计算抽至 `src/tools/amap/geo.py` 共用。
- **`TravelAssistant.plan_trip`**：参数抽取（结构化）→ 景点池 → 排程骨架 → ReAct 调研 → 结构化草稿 → Verifier 校验，未通过自动带 issues **自纠重试**（`PLAN_VERIFY_RETRIES`，默认 1 次）。
- **`POST /plan` 端点**：返回 plan / verification / schedule / params / budget_floor 结构化 JSON；失败 502 且不泄漏内部异常。

### 🚀 异步化

- **异步 HTTP 层**：`src/utils/http.py` 新增共享 `httpx.AsyncClient`（双重检查加锁）与 `acached_json_get`（TTL/负缓存语义与同步版一致）；httpx 转为运行时依赖。
- **工具 a- 变体**：天气 / POI（含预算过滤共享逻辑重构）/ 地理编码 / 驾车 / 公交 全部提供异步方法，错误语义与同步版一致（如定位失败抛 `RouteResolutionError`）。
- **端点异步化**：`/chat`（LangGraph `ainvoke` + 新增 `TravelAssistant.achat`，token 观测语义一致）与全部数据端点（weather/spots/food/hotels/route）改为 async def，不再占用线程池等待上游 IO。
- **压测脚本**：`benchmarks/bench_api.py`（纯标准库）——并发 RPS 与 p50/p95/p99 延迟分位数，为容量评估与后续优化提供量化基线。

### 🧠 向量语义记忆（可选）

- 新增 `src/memory/semantic.py`：GLM embeddings（`ZHIPUAI_EMBEDDING_MODEL`，默认 `embedding-2`，惰性初始化）+ 纯 Python 余弦库（无重型向量库依赖），JSON 持久化 + FIFO 上限（`SEMANTIC_MEMORY_MAX_ENTRIES`）。
- 接线：开启 `SEMANTIC_MEMORY_ENABLED` 后，每轮持久化用户需求原文，下轮跨会话语义召回相关行程并以 SystemMessage 注入；向量化失败静默降级不影响主流程；**默认关闭**。

### 🧪 测试与文档

- 新增 47 个用例（191 → 238 passed + 1 eval skip）：Verifier 全分支、逐日排程/预算拆分、plan_trip 管线（自纠/降级/异常传播）、异步 HTTP（httpx.MockTransport）、异步工具、语义记忆（召回排序/淘汰/持久化/接线）、/plan 端点；API 测试对齐异步契约（AsyncMock）。
- pytest 启用 `asyncio_mode=auto`；README 补 /plan 契约示例与压测章节；architecture.md 更新 Plan-and-Execute 与异步架构说明。

## [1.3.0] - 2026-11-07

### 🏗️ Agent 能力深化

- **工具层结构化升级**：10 个工具从「`Tool` + `"|"` 分隔符字符串协议」迁移为 `StructuredTool` + pydantic `args_schema`，LLM 通过原生 function calling 传 JSON 字段（city/origin/destination/spots 独立），消除分隔符歧义；工具名与行为保持不变。
- **用户偏好画像**：新增 `src/memory/profile.py`（规则抽取器 + 持久化），自动从对话中归纳目的地/天数/预算/兴趣标签，下一轮以 SystemMessage 注入实现个性化；仅持久化会话模式下维护，显式传历史的调用方不受影响。
- **历史窗口摘要**：新增 `src/memory/history.py`——近 N 条直传，更早消息默认压缩为规则摘要（保留预算/天数等关键约束，不再硬截断丢失）；支持注入 LLM 摘要器。
- **多景点就近优化**：`plan_multi_spot_route` 新增 `optimize_order`，按最近邻贪心重排游览顺序减少绕路（haversine 距离），API/工具均透传。
- **事实锚定**：SystemPrompt 明确要求「回答必须以工具返回的真实数据为依据」，抑制编造。

### ⚡ 流式输出

- **Agent 事件流**：新增 `TravelAssistant.astream_chat`，逐步产出 `tool_start` / `token` / `final` / `error` 事件（LangGraph `astream_events` v2）。
- **SSE 端点**：`POST /chat/stream`（text/event-stream），异常以 error 事件收尾并以 `[DONE]` 终止，客户端不会悬挂。
- **Web 进度 UI**：Streamlit 实时展示「正在调用工具：查询实时天气…」与 token 增量；新增侧栏会话 ID 管理（填写后历史与画像跨刷新持久化，可清空）。

### 📊 评估体系

- 新增 `evals/` 离线评估框架：**15 个黄金用例**（天气/POI/路线/综合规划/工具约束五维度）、工具调用记录器、启发式评分（工具覆盖 0.6 + 内容锚点 0.4）、**LLM-as-judge** 质量评分（相关性/事实依据/完整性/可操作性四维 rubric）。
- 运行入口 `python -m evals.runner [--judge] [--json] [--threshold]`；pytest 集成（`RUN_EVALS=1 pytest -m eval`，默认跳过）；评估对话写入临时目录，不污染运行时记忆。

### 🛡️ 安全与可观测性

- **工具输出防护栏**：新增 `src/utils/sanitize.py`，全部工具输出统一清洗——去控制字符/零宽字符（注入载体）、脱敏密钥形态（`sk-*`、32 位十六进制 key）、限长 4000。
- **token 用量观测**：新增 `TokenUsageHandler` 回调，每轮记录 prompt/completion/总 token 与 LLM 调用次数。
- **请求追踪**：所有 API 响应携带 `X-Request-ID`（透传或自动生成），访问日志含请求 ID。

### 🧰 工程与配置

- **SQLite 记忆后端**：`MEMORY_BACKEND=file|sqlite`，`SqliteMemory` 与 FileMemory 接口一致可无缝替换（单文件、事务性）。
- 新配置项：`MEMORY_BACKEND` / `AGENT_HISTORY_LIMIT` / `AGENT_HISTORY_CONTENT_MAX`。
- CI 新增 pip-audit 依赖漏洞审计任务（continue-on-error，仅报告）。
- pytest 注册 `eval` marker。

### 🧪 测试

- 新增 58 个用例（133 → 191 passed + 1 eval skip）：结构化工具契约与 schema 约束、防护栏、画像抽取/持久化、历史摘要、SQLite 后端、流式事件/错误收尾、SSE 端点、就近排序、request-id。

## [1.2.0] - 2026-11-07

### 🛡️ 安全与工程化（P0）

- **修复打包配置**：`pyproject.toml` 的 `build-backend` 由无效的 `setuptools.backends._legacy:_Backend` 改为 `setuptools.build_meta`，`pip install .` 恢复可用（此前直接报 `ModuleNotFoundError`）。
- **CI 可复现**：`requirements-dev.txt` 锁定精确版本（此前浮动版本导致新版本 ruff/black 引入新规则后 CI 漂移失败）；全量清零 63 处 lint 债务并统一 black 格式；ruff 配置迁移至 `[tool.ruff.lint]` 去除废弃告警。
- **API 访问控制（可选）**：新增 `API_AUTH_TOKEN` 环境变量，设置后所有端点要求 `Authorization: Bearer <token>`；未设置时保持完全开放（向后兼容）。
- **API 输入校验**：`/chat` 消息限长 2000 字符、历史消息限长 4000 且 `role` 白名单化；`page_size` 限定 1–25（高德 V5 上限）；`/route/multi-spot` 的 `mode` 收敛为 `driving|transit`。
- **错误契约统一**：上游失败返回 HTTP 502、定位失败返回 HTTP 400（此前一律 200 + `status=error`，客户端无法用 HTTP 语义区分）。
- **Docker 加固**：新增 `.dockerignore`（`.env` / `.git` / `.venv` 等不再进入构建上下文）；容器改为非 root 用户运行；增加 `HEALTHCHECK` 与 compose 健康检查；`.env` 卷挂载改只读；移除已废弃的 compose `version` 字段。

### 🤖 Agent 与健壮性（P1）

- **路线静默失败修复**：地名定位失败时抛 `RouteResolutionError` 返回可读提示（此前把原始地名静默传给高德，统一表现为"暂无路线信息"，LLM 无法据因调整）；高德 `status!="1"` 时记录原因并返回 None。
- **Agent 参数配置化**：`AGENT_TEMPERATURE` / `AGENT_MAX_TOKENS` / `AGENT_RECURSION_LIMIT` / `LLM_TIMEOUT` / `LLM_MAX_RETRIES` 全部接入 Settings；`agent.invoke` 显式传入 `recursion_limit`（默认 40，防止多工具攻略触顶 LangGraph 默认 25 导致循环中断）。
- **缓存上限与线程安全**：`TTLCache` 增加 `CACHE_MAX_SIZE`（FIFO 淘汰）与锁，消除长期运行内存无界增长；`get_session` 双重检查加锁；API 助手单例加锁。
- **配置缺口补齐**：新增 `LOG_LEVEL`（`DEBUG=true` 时仍强制 DEBUG）、`MEMORY_DIR`（Docker 卷挂载点可配）。
- **死代码清理**：删除 `models/travel.py` 中 9 个从未接线的模型类；移除 `travel_assistant.py` 内嵌的重复 CLI（统一走 `src/cli/main.py`）。

### 📊 可观测性与测试

- FastAPI 访问日志中间件（方法 / 路径 / 状态码 / 耗时）；`chat()` 记录会话耗时与输入输出长度。
- CI 新增 pytest-cov 覆盖率门禁（`--cov-fail-under=70`，当前 87%）。
- 新增 18 个测试用例：鉴权 401/放行、502/400 契约、请求校验 422、缓存 FIFO 淘汰、定位失败异常、recursion_limit 传递、运行时配置默认值（共 133 passed）。

### 📚 文档

- README：修正残留的 Windows 路径、补齐 `POST /route/multi-spot` 端点、新增响应契约 / 鉴权 / Docker 部署章节与调优配置表。
- 新增 `LICENSE`（MIT，与 pyproject 声明对齐）；版本号统一为 1.2.0（pyproject / FastAPI / `src.__version__`）。

## [1.1.1] - 2026-08-13

### 🐛 修复（P0 关键缺陷）

- **记忆并发安全 + 原子写**：`FileMemory` 新增进程内锁串行化「读-改-写」，写入改为「临时文件 + `os.replace` 原子替换」，避免 FastAPI 并发请求下历史静默丢失或崩溃写坏 JSON。
- **负缓存**：`cached_json_get` 现在仅缓存 `status=="1"` 的成功响应，高德短暂故障（`status=="0"`）不再被缓存整个 TTL，API 恢复后立即可重新请求。
- **异常脱敏**：Agent 与四个多参工具不再把原始异常文本（可能含 API key / 内部细节）拼进用户可见文案，改为 `logger.error(..., exc_info=True)` + 固定友好提示。
- **预算真实过滤**：`search_hotel_by_budget` 原先只做关键词映射、并无价格过滤；现按 `biz_ext.cost` 精确过滤区间（经济<300 / 舒适300-600 / 高档600-1000 / 豪华≥1000），cost 缺失条目保留。
- **HTML 标签剥离**：驾车/步行路线步骤改用正则 `_strip_tags` 剥离富文本标签，修复原先 `.replace("<","")` 产生 `b左转/b` 的畸形输出。

### ✨ 改进（P1 健壮性）

- 多景点 `transit` 模式缺少城市时返回明确错误，不再把景点名当城市传入。
- 公交工具缺少第 3 段城市时直接提示「请提供所在城市」，不再用 `destination` 兜底冒充城市。
- `ZHIPUAI_BASE_URL`、POI 类型码（110000/050000/100000）抽离为配置项/常量，去除硬编码与魔法数字。
- `_extract_response` 兼容 `AIMessage.content` 为 str 或内容块 list；无有效回复返回 `None`，且不把兜底文案持久化。
- session 文件名改为 `sha256(session_id)[:16]`（文件内记录原始 id），消除 `a/b` 与 `a.b` 清洗碰撞；`list_sessions` 排序返回。
- 路线数值转换改用 `_safe_int`/`_safe_float` 容错，非数字时长/距离不再中止整个规划。
- `weather.py` 格式化前对空 `lives`/`forecasts` 列表做守卫，避免 `IndexError`。
- 日志级别接入 `Settings.DEBUG`。

### 🧪 测试 / 工程

- 新增 `.github/workflows/ci.yml`（ruff / black --check / pytest）。
- 新增 `tests/unit/test_api.py`（FastAPI TestClient 覆盖 8 个端点）、`tests/unit/test_travel_assistant.py`。
- 重写 `test_tools.py`：真正调用各工具函数并断言行为，覆盖分隔符归一化与错误脱敏。
- 补齐 route（walking / strip_tags / transit 城市校验 / 数值容错）、weather（forecast 格式化）、memory（并发 / 原子写 / session 无碰撞）、poi（预算过滤边界）、http（负缓存）用例。
- dev 依赖新增 `httpx`；`mypy.disallow_untyped_defs` 由 `true` 改为 `false`（当前大量函数未标注返回类型）。

### 📚 文档

- `docs/architecture.md`：对齐 `create_react_agent` 实际参数，补充「哈希文件名 + 原子写」「预算过滤」「异常脱敏」设计说明。
- `README.md` / `.env.example`：补充 `ZHIPUAI_BASE_URL` 与预算过滤行为说明。

## [1.1.0] - 2026-06-19

### 🐛 修复（P0 功能性 Bug）

- **多景点路线规划**：原先直接把地名传给高德 `direction/driving`（要求坐标）导致静默失败。新增 `src/tools/amap/geocode.py` 地理编码模块，规划前先统一将地名转为经纬度，无法定位时返回明确错误提示。
- **驾车 / 公交路线**：起终点支持地名输入（自动经地理编码），移除了原先错误地把城市名赋给 `originid/destinationid` 的无效参数。
- **酒店 / 美食评分与价格取不到**：高德 V5 `place/text` 默认不返回 `biz_ext`。`search_food` / `search_hotel` / `search_hotel_by_budget` 现在显式传 `show_fields=biz_ext`，评分和参考价格可正常获取。
- **公交路线单位错误**：原先直接输出秒数和米数（如"3600 秒""500 米"）。新增 `_fmt_duration` / `_fmt_distance`，统一转为"分钟/小时""公里"，与驾车格式一致。

### ✨ 改进

- **接入持久化记忆**：`TravelAssistant.chat()` 现在按 `session_id` 接入 `FileMemory`，未显式传入 `chat_history` 时自动加载历史并在每轮结束后落盘，实现跨请求 / 跨进程的会话延续（修复了原先 `FileMemory` 形同虚设的死代码问题）。`FileMemory` 新增 `add_messages` 批量写入、`list_sessions` 会话列举，并对 `session_id` 做目录穿越净化。
- **共享 HTTP 客户端**：新增 `src/utils/http.py`，进程级 `requests.Session`（连接池 + 指数退避重试 429/5xx）+ 进程内 TTL 缓存，所有高德调用改走 `cached_json_get`，减少重复请求与配额浪费。
- **配置懒加载**：`src/config/settings.py` 改为 `@lru_cache` 的 `get_settings()`，避免未配 `.env` 时模块导入即崩溃；新增 `require_api_keys()` 供入口显式校验。保留模块级 `settings` 名称做向后兼容。
- **日志防重复**：`src/utils/logger.py` 增加 handler 存在性守卫与 `propagate=False`，解决多模块 import 后日志重复输出问题。
- **工具参数解析更健壮**：`tools/__init__.py` 统一将中文分隔符（`，`、`、`、`；`）归一为 `|`，缓解 LLM 输出中文逗号导致解析失败；驾车/公交工具可选附带城市参数。

### 🧪 测试

- 重写 `tests/conftest.py`，提供 `mock_http`（统一 mock 四个工具模块的 `cached_json_get`）与 `mock_env_vars` fixture。
- 新增 / 扩充测试覆盖：`test_geocode.py`、`test_http.py`、`test_memory.py`、`test_settings.py`、`test_logger.py`，以及 `tests/integration/test_assistant_memory.py`（验证记忆持久化与自动加载）。
- 全量测试 **75 passed**。

### 📚 文档

- 更新 `docs/architecture.md`：记忆系统、工具表（含 `show_fields`、地理编码）、项目结构、技术栈。
- 新增 `CHANGELOG.md`。
- `.gitignore` 增补 `memory/`（运行时记忆目录）与 `tests/.tmp/`（测试临时目录）。

## [1.0.0] - 2026

- 智能旅行助手首个发布版本：基于 LangGraph `create_react_agent` + GLM-5.1 + 高德地图 API，提供 CLI / Streamlit / FastAPI 三种入口。
