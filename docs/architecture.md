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

### 1. 推理引擎 — LLM（GLM-5.1 via ChatOpenAI）

`src/agents/travel_assistant.py:37-45`

- **职责**：所有"思考"的发生地——理解用户意图、决定调用哪个工具、如何传参、解读工具返回结果、生成最终攻略文本
- **输入**：SystemPrompt + 历史消息 + 用户消息 → 对话消息序列
- **输出**：要么是带 `tool_calls` 的 AIMessage（要求调用工具），要么是纯文本 AIMessage（最终回答）
- **关键参数**：`temperature=0.7`（生成多样性）、`max_tokens=4096`（支持长篇攻略）

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

### 4. 工具层 — 10 个 LangChain Tool

`src/tools/__init__.py` — 所有工具统一通过 `langchain_core.tools.Tool` 包装：

| 类别 | 工具名 | 底层实现 |
|------|--------|----------|
| 天气 | 查询实时天气 | `WeatherTool.get_weather()` → 高德 `weatherInfo?extensions=base` |
| 天气 | 查询天气预报 | `WeatherTool.get_weather_forecast()` → 高德 `weatherInfo?extensions=all` |
| 天气 | 查询穿搭建议 | `WeatherTool.get_dressing_advice()` — **本地规则引擎**，非 API |
| POI | 查询景点 | `POITool.search_scenic_spots()` → 高德 `place/text?types=110000` |
| POI | 查询美食 | `POITool.search_food()` → 高德 `place/text?types=050000&show_fields=biz_ext`（评分/人均） |
| POI | 查询住宿 | `POITool.search_hotel()` → 高德 `place/text?types=100000&show_fields=biz_ext`（评分/参考价） |
| POI | 按预算查询住宿 | `POITool.search_hotel_by_budget()` — 先关键词搜索，再按 `biz_ext.cost` 精确过滤价格区间 |
| 路线 | 驾车路线规划 | `RouteTool.get_driving_route()` → 高德 `direction/driving`（地名先经地理编码） |
| 路线 | 公交路线规划 | `RouteTool.get_transit_route()` → 高德 `direction/transit/integrated`（地名先经地理编码，需城市） |
| 路线 | 多景点路线规划 | `RouteTool.plan_multi_spot_route()` — 各景点先经地理编码再两两查询 |

每个 Tool 的标准结构：

```
Tool(name="xxx", func=回调函数, description="给LLM看的工具说明")
                                          └── LLM 根据这段描述
                                              决定何时、如何使用工具
```

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

- **持久化记忆**：`FileMemory` 按 `session_id` 把对话写入 `memory/<id>.json`，进程重启不丢失
- **哈希文件名**：文件名 = `sha256(session_id)[:16]`，既防目录穿越，也避免不同原始 id 清洗后碰撞；文件内容记录原始 `session_id` 供 `list_sessions()` 还原
- **原子写 + 进程内锁**：写入先落 `.json.tmp` 再 `os.replace` 原子替换，配合 `threading.Lock` 串行化读-改-写，避免并发丢历史或写坏 JSON
- **会话隔离**：不同 `session_id`（CLI / API / Web 各自的会话）互不干扰
- **显式优先**：调用方显式传入 `chat_history` 时跳过持久化读写，避免与外部状态重复
- **截断策略**：`[-8:]` 保留最近 8 条，每条 `[:500]` 截断长内容，控制 token 用量

### 6. 评估器 — 隐式存在于 LLM 推理中

该项目**没有独立的 Evaluator 模块**。评估是通过 LLM 的内省能力隐式完成的：

```
LLM 拿到工具返回 → 判断信息是否足够？
    ├── 不够 → 继续调用更多工具（进入下一轮 ReAct 循环）
    └── 足够 → 生成 Final Answer
```

`create_react_agent` 的 ReAct 循环由 LangGraph 状态机驱动（Agent Node ⇄ Tool Node），
当 LLM 不再输出 `tool_calls` 时循环终止。Agent 层在 `chat()` 中通过 try/except
兜底工具链异常，并返回脱敏后的友好提示（不向用户暴露内部异常细节）。

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
| 架构模式 | 单 Agent ReAct | 只能串行思考-执行-再思考，复杂任务轮次多 |
| 规划能力 | LLM 内隐规划 + SystemPrompt 模板 | 无显式 Planning 步骤，LLM 可能"遗漏"工具或信息 |
| 工具调用 | 10 个扁平 Tool 列表 | LLM 需要从 10 个工具中自行选择，容易选错参数格式 |
| 错误处理 | LLM 自行感知 + try/except | 工具失败后 LLM 可能重复重试或放弃，无自动恢复策略 |
| 记忆 | 文件持久化（按会话） | 当前仅本地文件，未接入向量检索 / 用户偏好画像 |
| 评估 | LLM 隐式判断 | 无法验证事实准确性、路线合理性、预算是否正确 |
| 并行能力 | Tool Node 支持并行执行 | 但 LLM 的单次决策仍然串行 |

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
│   │   ├── __init__.py               # FastAPI 路由定义
│   │   └── main.py                   # API 入口
│   └── cli/
│       └── main.py                   # 命令行界面
└── web/
    └── app.py                        # Streamlit Web 界面
```

## 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 推理引擎 | GLM-5.1（智谱AI） | 通过 OpenAI 兼容 API 调用 |
| Agent 框架 | LangGraph `create_react_agent` | ReAct 循环状态机 |
| 工具抽象 | `langchain_core.tools.Tool` | 工具定义与注册 |
| 消息类型 | `langchain_core.messages` | HumanMessage / AIMessage / SystemMessage / ToolMessage |
| 地图数据 | 高德地图 Web API | 天气 / POI 搜索 / 路线规划 / 地理编码 |
| Web 界面 | Streamlit | 聊天 UI + 侧边栏快速查询 |
| API 服务 | FastAPI | RESTful 接口 |
| 数据模型 | Pydantic v2 | 请求/响应结构定义 |
| 记忆存储 | 文件（JSON） | `FileMemory` 按会话 ID 落盘，跨进程持久化；哈希文件名 + 原子写 |
| HTTP 客户端 | requests Session | 连接池复用 + 指数退避重试 + TTL 缓存（仅缓存成功响应） |
