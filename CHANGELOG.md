# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
