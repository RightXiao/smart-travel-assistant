# 智能旅行助手 — Agent 架构文档

## 概述

本项目基于 **LangGraph `create_react_agent`** 实现 **ReAct 模式**（Reasoning + Acting 循环）的单 Agent 架构，使用 GLM-5.1 作为推理引擎，集成高德地图 API 提供天气、POI、路线等实时数据。

## 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                     TravelAssistant                      │
│                                                         │
│  ┌───────────────┐    ┌──────────────────────────────┐  │
│  │   SystemPrompt │    │    create_react_agent        │  │
│  │   (行为规范)    │───▶│    (LangGraph StateGraph)    │  │
│  └───────────────┘    │                              │  │
│                       │  ┌──────────────────────┐    │  │
│  ┌───────────────┐    │  │    Agent Node         │    │  │
│  │   GLM-5.1     │◀──▶│  │  (LLM 推理+决策)      │    │  │
│  │   (推理引擎)   │    │  └──────┬───────────────┘    │  │
│  └───────────────┘    │         │                    │  │
│                       │    has_tool_calls?            │  │
│  ┌───────────────┐    │    ┌────┴───────┐            │  │
│  │  10个 Tool     │◀───│   YES          NO           │  │
│  │  (高德API封装) │    │    │            │            │  │
│  └───────────────┘    │  ┌─┴────────┐  END          │  │
│                       │  │Tool Node │               │  │
│                       │  │(执行工具) │               │  │
│                       │  └────┬─────┘               │  │
│                       │       │返回Observation       │  │
│                       │       └───▶Agent Node        │  │
│                       └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
          ▲                    ▲
          │ chat_history       │ Tool调用
          │ (消息列表)          │ HTTP → 高德API
    ┌─────┴──────┐      ┌──────┴──────────┐
    │ Streamlit  │      │ 高德地图服务      │
    │ CLI / API  │      │ 天气/POI/路线    │
    └────────────┘      └─────────────────┘
```

---

## 各组件职责

### 1. 推理引擎 — LLM（多厂商 OpenAI 兼容接入 via ChatOpenAI）

**接入层**（`src/config/settings.py::resolve_llm_config` + `src/config/llm.py::build_chat_model`）：
`LLM_PROVIDER` 选择厂商预设（zhipuai / deepseek / qwen / moonshot / openai / ollama / custom），
`LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` 覆盖预设（未设置时回退 `ZHIPUAI_*`，保证向后兼容）。
Agent、评测 judge、语义记忆 embeddings 统一经工厂构建；`GET /config/llm`
对外展示生效配置（密钥脱敏）与全部厂商预设，前端页头/设置弹层实时呈现。

`src/agents/travel_assistant.py:37-45`

- **职责**：所有"思考"的发生地——理解用户意图、决定调用哪个工具、如何传参、解读工具返回结果、生成最终攻略文本
- **输入**：SystemPrompt + 历史消息 + 用户消息 → 对话消息序列
- **输出**：要么是带 `tool_calls` 的 AIMessage（要求调用工具），要么是纯文本 AIMessage（最终回答）
- **关键参数**（均通过 `Settings` 配置化，见 `.env.example`）：`AGENT_TEMPERATURE=0.7`（生成多样性）、`AGENT_MAX_TOKENS=4096`（支持长篇攻略）、`LLM_TIMEOUT=120` / `LLM_MAX_RETRIES=2`（请求超时与重试）

### 2. 规划器 / 行为规范 — SystemPrompt

`src/agents/travel_assistant.py:8-28`

- **职责**：定义 Agent 的"人格"和"输出标准"。不是独立的 Planner 模块，而是一段 Prompt，指导 LLM 如何规划：
    - 告诉 LLM 有哪些工具可用
    - 规定输出必须包含的 7 个模块（目的地概述 → 天气穿搭 → 景点 → 行程 → 美食 → 住宿 → 贴士）
    - 要求语气友好、内容具体详实
- **本质**：这是一个**静态规划模板**——LLM 按照这个纲要自行决定工具调用顺序和最终组织结构

### 3. 执行器 — LangGraph `create_react_agent` 内部状态机

`src/agents/travel_assistant.py:47-52`

- **职责**：LangGraph 预置的 ReAct 循环引擎。编译为一个 `CompiledStateGraph`（状态图），包含两个节点和一条条件边：

```
[Agent Node] ──has_tool_calls?──▶ [Tool Node] ──observation──▶ [Agent Node]
      │                                    (循环直到没有tool_calls)
      └── no tool_calls ──▶ END (返回最终回复)
```

- **Agent Node**：调用 LLM，传入当前消息列表，LLM 返回 `tool_calls` 或最终文本
- **Tool Node**：并行执行 LLM 请求的所有工具调用，将返回结果作为 `ToolMessage` 追加到消息列表
- **循环终止条件**：LLM 不再输出 `tool_calls`，仅输出文本
- **循环上限**：`agent.invoke` 显式传入 `config={"recursion_limit": Settings.AGENT_RECURSION_LIMIT}`（默认 40），防止 LLM 异常重试触发 LangGraph 默认 25 步上限后抛 `GraphRecursionError`

### 4. 工具层 — 10 个 StructuredTool（原生 function calling）

`src/tools/__init__.py` — 所有工具以 `StructuredTool` + pydantic `args_schema` 暴露：
LLM 通过原生 function calling 传结构化 JSON 字段（city / origin / destination /
spots 独立参数），替代早期「字符串 + `|` 分隔符」协议，消除分隔符歧义。
所有工具输出在返回 LLM 前统一经 `sanitize_tool_output` 清洗
（去控制/零宽字符、密钥脱敏、限长 4000）。

| 类别 | 工具名 | 底层实现 |
|------|--------|----------|
| 天气 | 查询实时天气 | `WeatherTool.get_weather()` → 高德 `weatherInfo?extensions=base` |
| 天气 | 查询天气预报 | `WeatherTool.get_weather_forecast()` → 高德 `weatherInfo?extensions=all` |
| 天气 | 查询穿搭建议 | `WeatherTool.get_dressing_advice()` — **本地规则引擎**，非 API |
| POI | 查询景点 | `POITool.search_scenic_spots()` → 高德 `place/text?types=110000` |
| POI | 查询美食 | `POITool.search_food()` → 高德 `place/text?types=050000&show_fields=biz_ext`（评分/人均） |
| POI | 查询住宿 | `POITool.search_hotel()` → 高德 `place/text?types=100000&show_fields=biz_ext`（评分/参考价） |
| POI | 按预算查询住宿 | `POITool.search_hotel_by_budget()` — 先关键词搜索，再按 `biz_ext.cost` 精确过滤价格区间 |
| 路线 | 驾车路线规划 | `RouteTool.get_driving_route()` → 高德 `direction/driving`（地名先经地理编码，无法定位抛 `RouteResolutionError` 返回可读提示） |
| 路线 | 公交路线规划 | `RouteTool.get_transit_route()` → 高德 `direction/transit/integrated`（地名先经地理编码，需城市） |
| 路线 | 多景点路线规划 | `RouteTool.plan_multi_spot_route()` — 各景点先经地理编码再两两查询 |

每个 Tool 的标准结构：

```
Tool(name="xxx", func=回调函数, description="给LLM看的工具说明")
                                          └── LLM 根据这段描述
                                              决定何时、如何使用工具
```

工具错误反馈约定：路线类工具对「地名无法定位」返回可读的原因提示（如
`无法定位起点：「xxx」…`），LLM 可据此引导用户修正输入；其余上游失败返回
「暂时无法获取」类兜底文案并记录 `logger.warning/error`。

### 5. 记忆系统 — 持久化对话历史

`src/agents/travel_assistant.py` + `src/memory/file_memory.py`

```
用户每次请求
   │
   ├─ chat_history 显式传入? ──YES──▶ 直接使用
   │                                   │
   └─ 未传入 ──▶ FileMemory.get_messages(session_id)  ──▶ 转换为
                                                          HumanMessage / AIMessage
                                                                  │
                                                                  ▼
                                                          agent.invoke({"messages": [...]})
                                                                  │
   本轮结束后（仅当未显式传 history 时）◀── assistant 回复
   └─ FileMemory.add_messages(session_id, [user, assistant])
        └─ 落盘：memory/<sha256(session_id)[:16]>.json（跨请求 / 跨进程持久化）
```

关键特征：

- **持久化记忆**：`FileMemory` 按 `session_id` 把对话写入 `<MEMORY_DIR>/<id>.json`（目录由 `Settings.MEMORY_DIR` 配置，默认 `memory/`），进程重启不丢失
- **哈希文件名**：文件名 = `sha256(session_id)[:16]`，既防目录穿越，也避免不同原始 id 清洗后碰撞；文件内容记录原始 `session_id` 供 `list_sessions()` 还原
- **原子写 + 进程内锁**：写入先落 `.json.tmp` 再 `os.replace` 原子替换，配合 `threading.Lock` 串行化读-改-写，避免并发丢历史或写坏 JSON
- **会话隔离**：不同 `session_id`（CLI / API / Web 各自的会话）互不干扰
- **显式优先**：调用方显式传入 `chat_history` 时跳过持久化读写，避免与外部状态重复
- **历史窗口摘要**：近 `AGENT_HISTORY_LIMIT`(默认 8) 条直传；更早消息经
  `src/memory/history.py` 压缩为「历史摘要」SystemMessage 前置注入
  （默认规则摘要，支持注入 LLM 摘要器），关键约束不再因截断丢失
- **用户画像**：`src/memory/profile.py` 规则抽取目的地/天数/预算/兴趣标签，
  按会话持久化到 `<MEMORY_DIR>/profiles/`，下轮以 SystemMessage 注入个性化；
  仅持久化会话模式维护（显式传 history 的调用方自管状态）
- **存储后端**：`MEMORY_BACKEND=file|sqlite`，`SqliteMemory` 接口与 FileMemory 一致

### 7. 行程规划子系统 — Plan-and-Execute + Verifier

自由聊天的质量由 LLM 内省保证；**结构化行程**（`POST /plan`）走确定性管线，
让"规划正确性"可以被机器校验：

```
用户需求
   │ 1. 参数抽取        llm.with_structured_output(TripRequestArgs)
   │ 2. 景点池          POITool.search_scenic_spots（名称+坐标 → 事实锚定白名单）
   │ 3. 排程骨架(Plan)  src/planner/itinerary.py：最近邻贪心排序 + 按天连续切块
   │                    + haversine 每日距离；预算下限 src/planner/budget.py
   │ 4. 调研(Execute)   ReAct Agent（天气/美食/住宿等工具）
   │ 5. 结构化草稿      llm.with_structured_output(TravelPlan)
   │ 6. Verifier        src/agents/verifier.py：
   │                      预算算术一致性（Σ日花费+住宿 == 总估算）
   │                      景点名锚定（景点 ∈ API 结果，幻觉防护）
   │                      预算上限告警
   │ 7. 自纠            未通过 → issues 回喂重新生成（PLAN_VERIFY_RETRIES）
   ▼
{plan, verification, schedule, params, budget_floor}
```

设计要点：排程与预算下限是**确定性代码**（可单测、无 LLM 方差）；LLM 只在
骨架上补充主题/花费/贴士；景点锚定把"编造景点"从概率问题变成可校验问题。

### 8. 异步化与可观测性

- **异步分层**：数据端点（weather/spots/food/hotels/route）async def + 工具
  a- 变体 + 共享 `httpx.AsyncClient`（`acached_json_get`，缓存/负缓存语义与
  同步一致）；对话端点 async def + LangGraph `ainvoke`（同步工具在执行器
  线程中运行，不阻塞事件循环）；`benchmarks/bench_api.py` 提供吞吐/延迟基线。
- **可观测性**：访问日志（方法/路径/状态/耗时 + X-Request-ID）、每轮 token
  用量（TokenUsageHandler）、行程规划耗时与自纠次数日志。

### 9. 评估体系 — 离线黄金用例 + LLM-as-judge

运行时评估由 LLM 内省完成（工具返回不够 → 继续 ReAct 循环）；**离线回归评估**
由 `evals/` 框架承担：

```
python -m evals.runner [--judge] [--json] [--threshold 0.7]

用例（15 个，五能力维度）
   │  TravelAssistant(临时记忆后端) + 工具调用记录器
   ▼
启发式评分 = 0.6×工具覆盖(必备工具是否被调用) + 0.4×内容锚点(关键信息是否出现)
   │  可选 --judge
   ▼
LLM-as-judge：相关性 / 事实依据 / 完整性 / 可操作性 四维 rubric，温度 0 可复现
   ▼
报告 + 阈值门禁（CI 可消费 JSON；pytest 集成 RUN_EVALS=1 pytest -m eval）
```

运行时兜底不变：`chat()` 通过 try/except 捕获工具链异常，返回脱敏的友好提示。

---

## 完整交互时序

以用户输入"我想去杭州玩2天，预算2000元"为例：

```
时间线 ──────────────────────────────────────────────────────────────▶

用户          Streamlit          TravelAssistant     LangGraph ReAct     LLM(GLM)        高德API
 │                │                    │                   │                │              │
 ├─输入──────────▶│                    │                   │                │              │
 │                ├─chat(prompt,──────▶│                   │                │              │
 │                │  history)          │                   │                │              │
 │                │                    ├─invoke(──────────▶│                │              │
 │                │                    │  messages)        │                │              │
 │                │                    │                   ├─Agent Node────▶│              │
 │                │                    │                   │ messages       │              │
 │                │                    │                   │                ├─思考────────▶│
 │                │                    │                   │                │ "需要天气、  │
 │                │                    │                   │                │  景点信息"    │
 │                │                    │                   │◀─tool_calls────┤              │
 │                │                    │                   │                │              │
 │                │                    │                   ├─Tool Node──────┼──────────────▶│
 │                │                    │                   │ 执行查询天气    │   高德天气API │
 │                │                    │                   │◀───────────────┼───────────────┤
 │                │                    │                   │ 杭州: 25℃ 晴   │              │
 │                │                    │                   ├─Tool Node──────┼──────────────▶│
 │                │                    │                   │ 执行查询景点    │   高德POI API│
 │                │                    │                   │◀───────────────┼───────────────┤
 │                │                    │                   │ 西湖/太子湾... │              │
 │                │                    │                   │                │              │
 │                │                    │                   ├─Agent Node────▶│              │
 │                │                    │                   │ +observation   │              │
 │                │                    │                   │                ├─继续思考────▶│
 │                │                    │                   │                │ "还需要美食、 │
 │                │                    │                   │                │  住宿信息"    │
 │                │                    │                   │◀─tool_calls────┤              │
 │                │                    │                   │                │              │
 │                │                    │                   ├─Tool Node x2───┼──────────────▶│
 │                │                    │                   │ 美食+住宿       │   POI API x2 │
 │                │                    │                   │◀───────────────┼───────────────┤
 │                │                    │                   │                │              │
 │                │                    │                   ├─Agent Node────▶│              │
 │                │                    │                   │                ├─综合判断─────│
 │                │                    │                   │                │ "信息足够"    │
 │                │                    │                   │◀─Final Answer──┤              │
 │                │                    │                   │ 完整攻略文本     │              │
 │                │                    │◀──────────────────┤                │              │
 │                │◀───────────────────│                   │                │              │
 │◀─显示攻略──────┤                    │                   │                │              │
```

---

## 架构评价

| 维度 | 现状 | 局限 |
|------|------|------|
| 架构模式 | 单 Agent ReAct + Plan-and-Execute 结构化规划 | 聊天路径仍是串行思考-执行-再思考 |
| 规划能力 | 确定性排程骨架 + 结构化输出 + Verifier 自纠 | 多日排程为贪心近似（非全局最优 TSP）；营业时间/门票未接入 |
| 工具调用 | 10 个 StructuredTool（function calling 结构化参数） | 参数歧义已消除；工具选择的准确性由评估集持续验证 |
| 错误处理 | 定位失败可读提示 + Verifier 自纠 + try/except 兜底 | 工具失败后仍依赖 LLM 自行调整，无自动重试策略 |
| 记忆 | file/sqlite 后端 + 用户画像 + 历史摘要 + **向量语义记忆（可选）** | 语义库为线性扫描，规模增长后需换专业向量库 |
| IO 模型 | 数据端点/对话端点 async + 异步工具层 | ReAct 循环内同步工具在执行器线程运行（LangGraph 默认） |
| 评估 | 15 用例启发式评分 + LLM-as-judge | 用例集规模有限，可随线上问题持续扩充 |

---

## 项目结构

```
Experiment/
├── .env.example                      # 环境变量示例
├── requirements.txt                  # Python 依赖
├── README.md                         # 项目说明
├── docs/
│   └── architecture.md               # 本文档
├── src/
│   ├── __init__.py
│   ├── config/
│   │   └── settings.py               # 配置管理（环境变量读取）
│   ├── models/
│   │   └── travel.py                 # Pydantic 数据模型
│   ├── agents/
│   │   └── travel_assistant.py       # 旅行助手 Agent（核心，接入 FileMemory）
│   ├── memory/
│   │   ├── base.py                   # 记忆系统抽象基类
│   │   └── file_memory.py            # 文件持久化记忆（跨会话）
│   ├── tools/
│   │   ├── __init__.py               # 工具注册（10个LangChain Tool）
│   │   └── amap/
│   │       ├── geocode.py            # 地理编码（地名 → 经纬度，带缓存）
│   │       ├── weather.py            # 天气查询 / 预报 / 穿搭建议
│   │       ├── poi.py                # POI 搜索（景点/美食/酒店，含评分价格）
│   │       └── route.py              # 路线规划（驾车/公交/多景点，统一时间距离格式化）
│   ├── utils/
│   │   ├── logger.py                 # 日志（防重复 handler）
│   │   └── http.py                   # 共享 Session（重试）+ TTL 缓存
│   ├── api/
│   │   ├── __init__.py               # FastAPI 路由定义 + /web 静态前端挂载
│   │   └── main.py                   # API 入口
│   └── cli/
│       └── main.py                   # 命令行界面
└── web/
    ├── static/                       # 全新零构建前端（SPA：攻略定制主流程，FastAPI /web 托管）
    └── app.py                        # Streamlit Web 界面（保留共存）
```

## 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 推理引擎 | 多厂商 OpenAI 兼容接入 | 默认 GLM-5.1，`LLM_PROVIDER` 一键切换（预设表见 settings） |
| Agent 框架 | LangGraph `create_react_agent` | ReAct 循环状态机 |
| 工具抽象 | `langchain_core.tools.StructuredTool` | args_schema 结构化参数 + function calling |
| 消息类型 | `langchain_core.messages` | HumanMessage / AIMessage / SystemMessage / ToolMessage |
| 地图数据 | 高德地图 Web API | 天气 / POI 搜索 / 路线规划 / 地理编码 |
| Web 界面 | 原生 HTML/CSS/JS（零构建） | 攻略定制主流程 SPA，FastAPI `StaticFiles` 挂载 `/web` |
| 旧版 Web 界面 | Streamlit | 聊天 UI + 侧边栏快速查询（保留共存） |
| API 服务 | FastAPI | RESTful 接口 |
| 数据模型 | Pydantic v2 | 请求/响应结构定义 |
| 记忆存储 | 文件 / SQLite / 语义向量 | 会话记忆（file/sqlite）+ 用户画像 + 跨会话语义召回（纯 Python 余弦库） |
| 异步 IO | httpx.AsyncClient | 共享连接池 + TTL 缓存复用；数据/对话端点全 async |
| HTTP 客户端 | requests Session / httpx | 同步（ReAct 工具内）与异步（数据端点）双通道，缓存语义一致 |
