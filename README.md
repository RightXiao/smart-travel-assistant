# 🧳 智能旅行助手

基于 Python + LangChain + GLM-5.1 + 高德地图 API 构建的智能旅行助手，能够根据用户提供的目的地、旅行时间、预算等信息，生成完整的旅游攻略。

## ✨ 功能特性

- 🌤️ **实时天气查询** - 集成高德地图API获取实时天气和穿搭建议
- 🏛️ **景点推荐** - 智能推荐目的地热门景点
- 🗺️ **路线规划** - 多个景点之间的最优路线规划（地名自动定位，无需手填坐标）
- 🍜 **美食推荐** - 当地特色美食介绍（含评分 / 人均参考）
- 🏨 **住宿建议** - 根据预算推荐合适的住宿（含评分 / 参考价，按价格区间真实过滤）
- 💬 **智能对话** - 支持自然语言多轮对话，并按会话持久化记忆（进程重启不丢失）
- 🖥️ **多界面支持** - 提供命令行界面(CLI)、Web界面(Streamlit)和 RESTful API(FastAPI)

## 🛠️ 技术栈

- **后端**: Python 3.9+
- **AI框架**: LangChain / LangGraph（ReAct Agent）
- **LLM**: GLM-5.1 (智谱AI)
- **Web框架**: Streamlit / FastAPI
- **地图服务**: 高德地图API（天气 / POI / 路线 / 地理编码）
- **记忆存储**: 文件持久化（按会话）
- **依赖管理**: pip

## 📦 安装

### 1. 克隆项目

```bash
cd d:\Experiment
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

- **智谱AI API Key**: 访问 [https://open.bigmodel.cn/](https://open.bigmodel.cn/) 注册并获取
- **高德地图API Key**: 访问 [https://lbs.amap.com/](https://lbs.amap.com/) 注册并获取

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
copy .env.example .env
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
DEBUG=true
```

## 🚀 使用方法

### 方式一：Web界面（推荐）

启动Streamlit Web应用：

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
| GET  | `/weather/{city}` | 实时天气 / 预报（`?forecast=true`） |
| GET  | `/spots/{city}` | 景点搜索 |
| GET  | `/food/{city}` | 美食搜索 |
| GET  | `/hotels/{city}` | 酒店（可 `?budget=经济型`） |
| GET  | `/route/driving` | 驾车路线（`?origin=..&destination=..`） |
| GET  | `/route/transit` | 公交路线（`?origin=..&destination=..&city=..`） |

访问 `http://localhost:8000/docs` 查看交互式 API 文档。

## 📂 项目结构

```
d:\Experiment\
├── .env                              # 环境变量配置（需自行创建）
├── .env.example                      # 环境变量配置示例
├── requirements.txt                  # Python依赖
├── README.md                         # 项目说明
├── src/
│   ├── __init__.py
│   ├── config/                       # 配置模块
│   │   ├── __init__.py
│   │   └── settings.py              # 配置管理
│   ├── agents/                       # Agent实现
│   │   ├── __init__.py
│   │   └── travel_assistant.py      # 旅行助手Agent（接入持久化记忆）
│   ├── memory/                       # 记忆系统
│   │   └── file_memory.py            # 文件持久化（按会话）
│   ├── tools/                        # 工具模块
│   │   ├── __init__.py               # 工具整合
│   │   └── amap/                     # 高德地图工具
│   │       ├── geocode.py            # 地理编码（地名→坐标）
│   │       ├── weather.py            # 天气查询
│   │       ├── route.py              # 路线规划
│   │       └── poi.py                # POI搜索（含评分价格）
│   ├── utils/                        # 通用工具
│   │   ├── logger.py                 # 日志
│   │   └── http.py                   # 共享Session + 重试 + 缓存
│   ├── api/                          # FastAPI 接口
│   └── cli/                          # 命令行界面
│       ├── __init__.py
│       └── main.py
└── web/                               # Web界面
    └── app.py                        # Streamlit应用
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
