# 🧳 智能旅行助手

基于 Python + LangChain + 高德地图 API 构建的智能旅行助手，**灵活接入各家大模型**（智谱 / DeepSeek / 通义 / Kimi / OpenAI / Ollama / 自建 OpenAI 兼容端点），能够根据用户提供的目的地、旅行时间、预算等信息，生成完整的旅游攻略。

## ✨ 功能特性

- 🌤️ **实时天气查询** - 集成高德地图API获取实时天气和穿搭建议
- 🏛️ **景点推荐** - 智能推荐目的地热门景点
- 🗺️ **路线规划** - 多个景点之间的最优路线规划（地名自动定位，支持按地理位置就近优化游览顺序）
- 🍜 **美食推荐** - 当地特色美食介绍（含评分 / 人均参考）
- 🏨 **住宿建议** - 根据预算推荐合适的住宿（含评分 / 参考价，按价格区间真实过滤）
- 💬 **智能对话** - 多轮对话 + 会话持久化记忆（file / sqlite 后端）+ **用户偏好画像**（自动记忆目的地/天数/预算/兴趣，个性化推荐）
- 🗓️ **结构化行程规划** - Plan-and-Execute：地理就近逐日排程 + `with_structured_output` 强制 TravelPlan schema + **Verifier 校验**（预算算术/景点名锚定，未通过自动自纠），`POST /plan` 返回结构化 JSON
- ⚡ **流式输出** - 工具调用进度与回复 token 实时展示（SSE 端点 + Web 进度 UI）
- 🚀 **异步化 API** - 数据端点走 httpx.AsyncClient + 工具异步变体，对话走 LangGraph `ainvoke`；内置轻量压测脚本量化吞吐
- 🧠 **向量语义记忆**（可选）- 跨会话语义召回相关历史行程（GLM embeddings，默认关闭）
- 🛡️ **防护栏** - 工具输出统一清洗（控制字符/密钥脱敏/限长），token 用量观测
- 📊 **离线评估** - 黄金用例集 + 工具选择评分 + LLM-as-judge（`python -m evals.runner`）
- 🖥️ **多界面支持** - 提供全新零构建 Web 界面（攻略定制主流程）、命令行界面(CLI)、Web界面(Streamlit)和 RESTful API(FastAPI)
- 🎨 **全新 Web 前端** - 需求定制表单 → 可视化定制进度 → 结构化行程结果 → 逐日详情；含偏好回显、预算拆分、AI 助手抽屉与完整空/错/加载状态（`/web/?mock=1` 可无 Key 演示）
- 🔌 **多厂商模型接入** - 通过 `LLM_PROVIDER` 一键切换智谱 / DeepSeek / 通义 / Kimi / OpenAI / Ollama / 自建端点，`GET /config/llm` 展示当前接入（密钥脱敏），前端页头实时显示

## 🛠️ 技术栈

- **后端**: Python 3.9+
- **AI框架**: LangChain / LangGraph（ReAct Agent，StructuredTool function calling）
- **LLM**: 多厂商 OpenAI 兼容接入（默认 GLM-5.1，可切换 DeepSeek / 通义 / Kimi / OpenAI / Ollama / 自建）
- **Web框架**: FastAPI（SSE 流式 + 静态托管全新前端）/ Streamlit
- **地图服务**: 高德地图API（天气 / POI / 路线 / 地理编码）
- **记忆存储**: 文件 / SQLite（按会话，含用户画像）
- **依赖管理**: pip

## 📦 安装

### 1. 克隆项目

```bash
git clone https://github.com/RightXiao/smart-travel-assistant.git
cd smart-travel-assistant
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv

# Windows 激活虚拟环境
venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

## ⚙️ 配置

### 1. 获取API密钥

- **LLM API Key**：按所选厂商获取（默认智谱 [https://open.bigmodel.cn/](https://open.bigmodel.cn/)；DeepSeek / 阿里云百炼 / Moonshot / OpenAI 平台同理；Ollama 本地运行无需 Key）
- **高德地图API Key**: 访问 [https://lbs.amap.com/](https://lbs.amap.com/) 注册并获取

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env        # Windows 用: copy .env.example .env
```

编辑 `.env` 文件，填入你的API密钥：

```env
# 智谱AI API配置
ZHIPUAI_API_KEY=your_zhipuai_api_key_here
ZHIPUAI_MODEL=glm-5.1
# ZHIPUAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/   # OpenAI 兼容端点（可选，默认值）

# 高德地图API配置
AMAP_API_KEY=your_amap_api_key_here

# 应用配置
APP_NAME=智能旅行助手
DEBUG=false
```

### 3. 多厂商模型接入（LLM_*，核心配置）

通过 OpenAI 兼容端点灵活接入各家大模型，`GET /config/llm` 可查看当前生效配置：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LLM_PROVIDER` | `zhipuai` | `zhipuai` / `deepseek` / `qwen` / `moonshot` / `openai` / `ollama` / `custom` |
| `LLM_API_KEY` | 回退 `ZHIPUAI_API_KEY` | 所选厂商的 API Key（ollama 本地服务可不设） |
| `LLM_MODEL` | 厂商预设默认 | 模型名；**切换厂商时建议显式设置**（各厂商模型名不通用） |
| `LLM_BASE_URL` | 厂商预设 | OpenAI 兼容端点；`custom` 必填（vLLM / LM Studio 等） |
| `EMBEDDING_MODEL` | 回退 `ZHIPUAI_EMBEDDING_MODEL` | 语义记忆 embeddings 模型 |

切换示例（DeepSeek）：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat
```

优先级：`LLM_*` > `ZHIPUAI_*`（智谱专属回退）> 厂商预设默认值。Agent / 评测 judge / 语义记忆 embeddings 统一走该配置。

### 4. 可选调优配置（均有默认值，按需覆盖）

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HTTP_TIMEOUT` | `10` | 高德 API 请求超时（秒） |
| `HTTP_MAX_RETRIES` | `3` | 高德请求失败重试次数（429/5xx 指数退避） |
| `CACHE_TTL` | `1800` | POI / 天气结果缓存有效期（秒） |
| `CACHE_MAX_SIZE` | `512` | 进程内缓存最大条目数（FIFO 淘汰） |
| `AGENT_TEMPERATURE` | `0.7` | LLM 生成多样性 |
| `AGENT_MAX_TOKENS` | `4096` | 单次回复最大 token |
| `AGENT_RECURSION_LIMIT` | `40` | ReAct 循环步数上限 |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | `120` / `2` | LLM 请求超时与重试 |
| `LOG_LEVEL` | `INFO` | 日志级别（`DEBUG=true` 时强制 DEBUG） |
| `MEMORY_DIR` | `memory` | 会话记忆存储目录 |
| `MEMORY_BACKEND` | `file` | 会话记忆后端：`file` / `sqlite` |
| `AGENT_HISTORY_LIMIT` | `8` | 直传 LLM 的历史条数（更早消息压缩为摘要） |
| `AGENT_HISTORY_CONTENT_MAX` | `500` | 单条历史内容截断长度 |
| `API_AUTH_TOKEN` | 空 | 设置后所有 API 端点要求 `Authorization: Bearer <token>` |

## 🚀 使用方法

### 方式一：Web界面（推荐）

**全新攻略定制前端**（与 API 同进程，零构建）：

```bash
uvicorn src.api.main:app --reload
```

浏览器访问 `http://localhost:8000/web/`（直接访问根路径 `http://localhost:8000/`
也会自动跳转到该页面）：填写目的地 / 天数 / 预算 / 偏好，即可获得经过校验的
结构化逐日行程，并支持逐日详情、真实路线查询与 AI 助手追问。
无 API Key 时可访问 `http://localhost:8000/web/?mock=1` 体验演示模式（内置模拟数据）。

> **Windows + WSL 打不开？** 在 Windows PowerShell 中执行
> `curl http://localhost:8000/` 验证转发；若不通，用 `wsl hostname -I`
> 获取 WSL IP，改访 `http://<WSL_IP>:8000/web/`。

**Streamlit 旧版界面**（聊天式，保留共存）：

```bash
streamlit run web/app.py
```

然后在浏览器中访问显示的URL（通常是 `http://localhost:8501`）

### 方式二：命令行界面（CLI）

#### 交互模式

```bash
python -m src.cli.main
```

#### 直接提问

```bash
python -m src.cli.main "我想去北京旅游3天，预算5000元"
```

### 方式三：Python代码调用

```python
from src.agents.travel_assistant import TravelAssistant

assistant = TravelAssistant()
# 不传 chat_history 时，按 session_id 自动持久化记忆
response = assistant.chat("我想去上海玩，有什么推荐吗？", session_id="my-trip")
print(response)
```

### 方式四：RESTful API（FastAPI）

```bash
uvicorn src.api.main:app --reload
```

主要端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 多轮对话（支持带 `chat_history`） |
| POST | `/chat/stream` | 流式对话（SSE：工具进度 / token / final 事件） |
| POST | `/plan` | **结构化行程规划**（Plan-and-Execute + Verifier 校验） |
| GET  | `/weather/{city}` | 实时天气 / 预报（`?forecast=true`） |
| GET  | `/spots/{city}` | 景点搜索（`?page_size=1..25`） |
| GET  | `/food/{city}` | 美食搜索 |
| GET  | `/hotels/{city}` | 酒店（可 `?budget=经济型`） |
| GET  | `/route/driving` | 驾车路线（`?origin=..&destination=..`） |
| GET  | `/route/transit` | 公交路线（`?origin=..&destination=..&city=..`） |
| POST | `/route/multi-spot` | 多景点路线（body: `{spots, city, mode, optimize_order}`） |
| GET  | `/config/llm` | 当前多厂商 LLM 接入配置（密钥脱敏 + 厂商预设） |

**结构化行程规划**（`POST /plan`，body: `{"message": "杭州2天预算2000"}`）返回：

```json
{
  "status": "ok",
  "data": {
    "plan":         {"destination": "杭州", "days": 2, "day_plans": [...], "total_estimated_cost": 1000, ...},
    "verification": {"ok": true, "issues": [], "warnings": [], "over_budget": false},
    "schedule":     [{"day": 1, "spots": ["西湖", "苏堤"], "est_distance_km": 5.2}],
    "params":       {"destination": "杭州", "days": 2, "budget": 2000},
    "budget_floor": {"food_total": 300, "transit_total": 13, "total": 313}
  }
}
```

管线：参数抽取（结构化）→ 高德景点池（事实锚定白名单）→ 地理就近逐日排程 →
ReAct 调研 → `TravelPlan` 结构化草稿 → Verifier 校验预算算术与景点锚定，
未通过自动带 issues 自纠（`PLAN_VERIFY_RETRIES`，默认 1 次）。

**SSE 事件格式**（`POST /chat/stream`，`data: <json>\n\n`）：

```
{"type": "tool_start", "name": "查询实时天气"}   # 工具开始
{"type": "token", "content": "..."}             # 回复 token
{"type": "final", "content": "完整回复"}         # 收尾事件
data: [DONE]
```

所有响应携带 `X-Request-ID` 头，便于日志追踪。

**响应契约**：成功返回 HTTP 200 + `{"status": "ok", ...}`；上游服务失败返回
HTTP 502 + `{"status": "error", "message": ...}`；参数错误（如地名无法定位）
返回 HTTP 400；请求体校验失败返回 HTTP 422。

**鉴权（可选）**：设置环境变量 `API_AUTH_TOKEN` 后，所有端点要求
`Authorization: Bearer <token>` 请求头；未设置时不启用（本地开发友好）。

访问 `http://localhost:8000/docs` 查看交互式 API 文档。

### 方式五：Docker 部署

```bash
# 构建并启动 API (8000) 与 Streamlit (8501)
docker compose up -d --build

# 查看健康状态
docker compose ps
```

记忆数据持久化在命名卷 `memory` 中；`.env` 以只读方式挂载进容器，
不会被构建进镜像（已通过 `.dockerignore` 排除）。

### 离线评估（Agent 质量回归）

内置黄金用例集（15 个用例，覆盖天气 / POI / 路线 / 综合规划 / 工具约束五个能力维度），
用于 prompt / 模型 / 工具变更后的回归验证：

```bash
# 启发式评分（工具选择 + 内容锚点，需真实 API Key）
python -m evals.runner

# 叠加 LLM-as-judge 质量评分（相关性/事实依据/完整性/可操作性）
python -m evals.runner --judge

# JSON 报告 + 阈值门禁（低于 0.7 退出码 1，供 CI 消费）
python -m evals.runner --json --threshold 0.7
```

pytest 集成（默认跳过，设置 `RUN_EVALS` 启用）：

```bash
RUN_EVALS=1 pytest -m eval -q
```

### 性能压测

内置标准库压测脚本（无额外依赖），用于量化吞吐基线、评估扩容/异步化收益：

```bash
# 1. 启动服务
uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# 2. 20 并发 × 200 请求打根端点（无外部依赖、不耗配额）
python benchmarks/bench_api.py --concurrency 20 --requests 200

# 指定路径与鉴权
python benchmarks/bench_api.py --path /spots/北京 --token $API_AUTH_TOKEN
```

输出 RPS 与 p50/p95/p99 延迟分位数。

## 📂 项目结构

```
smart-travel-assistant/
├── .env                              # 环境变量配置（需自行创建，不入库）
├── .env.example                      # 环境变量配置示例
├── requirements.txt                  # 运行时依赖
├── requirements-dev.txt              # 开发依赖（锁定版本）
├── pyproject.toml                    # 打包与工具链配置
├── Dockerfile / docker-compose.yml   # 容器化部署
├── README.md                         # 项目说明
├── CHANGELOG.md                      # 变更日志
├── LICENSE                           # MIT 许可证
├── docs/
│   └── architecture.md               # Agent 架构文档
├── evals/                            # 离线评估框架（黄金用例 / 评分器 / judge）
├── benchmarks/                       # 性能压测脚本（标准库）
├── tests/                            # 单元 / 集成 / 评估测试（覆盖率 89%+）
├── src/
│   ├── __init__.py                   # 版本号统一维护
│   ├── config/                       # 配置模块（pydantic-settings）
│   ├── agents/                       # Agent（ReAct + 记忆 + 画像 + 流式 + plan_trip）
│   ├── planner/                      # 确定性引擎（逐日排程 / 预算拆分）
│   ├── memory/                       # 记忆系统（file/sqlite + 画像 + 摘要 + 语义向量）
│   ├── tools/                        # 工具模块（StructuredTool + 同步/异步双通道）
│   ├── utils/                        # 通用工具（日志/HTTP缓存/防护栏/token观测）
│   ├── models/                       # API 契约 + 行程结构化输出 schema
│   ├── api/                          # FastAPI（异步端点 / 鉴权 / SSE / /plan）
│   └── cli/                          # 命令行界面
└── web/                              # Web界面
    ├── static/                       # 全新零构建前端（SPA：定制表单/进度/结果/详情，FastAPI /web 托管）
    └── app.py                        # Streamlit 界面（旧版聊天式，保留共存）
```

## 💡 使用示例

### 示例1：基础旅行规划

**用户输入**：
```
我想去北京旅游3天，预算5000元
```

**助手回复**：
```
📍 目的地概述
北京是中国的首都，拥有丰富的历史文化遗产...

🌤️ 天气情况和穿搭建议
当前天气晴朗，气温15-25℃，建议穿着薄外套...

🏛️ 精选景点介绍
1. 故宫博物院 - 明清两代皇宫
2. 八达岭长城 - 万里长城精华段
...

🗺️ 推荐路线规划
Day 1: 天安门广场 → 故宫 → 景山公园
Day 2: 八达岭长城 → 明十三陵
Day 3: 颐和园 → 圆明园
...
```

### 示例2：美食之旅

**用户输入**：
```
成都美食之旅推荐
```

## 🔧 常见问题

### Q: API调用失败怎么办？
A: 请检查 `.env` 文件中的API密钥是否正确配置，并确保账户有足够的余额。

### Q: 如何修改使用的模型？
A: 修改 `.env` 文件中的 `ZHIPUAI_MODEL` 配置项即可。

### Q: 支持哪些城市的查询？
A: 支持高德地图API覆盖的所有中国城市。

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**注意**: 使用前请确保已正确配置所有API密钥。
