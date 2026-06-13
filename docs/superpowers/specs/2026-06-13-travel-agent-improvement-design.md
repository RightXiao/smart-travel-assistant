# 旅行代理项目全面改进设计文档

## 1. 概述

本文档描述了对 `travel-agent` 项目的全面改进设计方案，采用三阶段渐进式改进策略，旨在修复核心缺陷、提升代码质量、增强功能，并支持基础部署。

### 1.1 改进目标

- 修复核心缺陷，确保项目可正常运行
- 采用 Google 代码风格，提升代码质量和可维护性
- 实现全面测试覆盖，确保功能正确性
- 增强功能，包括记忆系统、流式响应、步行路线
- 支持基础 Docker 部署

### 1.2 改进策略

采用三阶段渐进式改进策略：

1. **阶段1：核心缺陷修复** - 修复依赖缺失、API架构问题、公交路线Bug
2. **阶段2：质量提升与测试** - 采用Google风格、添加测试、统一日志、完善打包
3. **阶段3：功能增强与部署** - 实现记忆系统、流式响应、步行路线、Docker部署

## 2. 整体架构改进

### 2.1 依赖管理改进

**当前问题**：
- 缺少 `langgraph` 依赖
- 包含未使用的 `zhipuai` 依赖
- 版本号过于宽松

**改进方案**：

```txt
# requirements.txt
langchain>=0.1.0,<1.0.0
langchain-openai>=0.0.5,<1.0.0
langchain-core>=0.1.0,<1.0.0
langgraph>=0.2.0,<1.0.0
fastapi>=0.109.0,<1.0.0
uvicorn>=0.27.0,<1.0.0
streamlit>=1.30.0,<2.0.0
requests>=2.31.0,<3.0.0
python-dotenv>=1.0.0,<2.0.0
pydantic>=2.5.0,<3.0.0
pydantic-settings>=2.0.0,<3.0.0
```

```txt
# requirements-dev.txt
pytest>=7.0.0,<8.0.0
pytest-asyncio>=0.21.0,<1.0.0
black>=23.0.0,<24.0.0
ruff>=0.1.0,<1.0.0
mypy>=1.0.0,<2.0.0
```

### 2.2 项目结构改进

**当前结构**：
```
src/
├── agents/
├── api/
├── cli/
├── config/
├── models/
└── tools/
```

**改进结构**：
```
travel-agent/
├── src/
│   ├── agents/
│   ├── api/
│   ├── cli/
│   ├── config/
│   ├── models/
│   ├── tools/
│   ├── utils/          # 新增：通用工具函数
│   └── services/       # 新增：业务逻辑服务层
├── tests/              # 新增：测试目录（项目根目录下）
├── docs/
├── requirements.txt
├── pyproject.toml
└── README.md
```

### 2.3 配置管理改进

**当前问题**：`Settings` 类在模块加载时就获取环境变量，不够灵活

**改进方案**：使用 Pydantic BaseSettings

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ZHIPUAI_API_KEY: str
    ZHIPUAI_MODEL: str = "glm-5.1"
    AMAP_API_KEY: str
    APP_NAME: str = "智能旅行助手"
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# 全局单例
settings = Settings()
```

## 3. 阶段1：核心缺陷修复

### 3.1 依赖修复

**文件修改**：`requirements.txt`

```txt
# 移除未使用的依赖
# zhipuai>=2.0.0

# 添加缺失的依赖
langgraph>=0.2.0,<1.0.0

# 为所有依赖添加版本上限
langchain>=0.1.0,<1.0.0
langchain-openai>=0.0.5,<1.0.0
langchain-core>=0.1.0,<1.0.0
fastapi>=0.109.0,<1.0.0
uvicorn>=0.27.0,<1.0.0
streamlit>=1.30.0,<2.0.0
requests>=2.31.0,<3.0.0
python-dotenv>=1.0.0,<2.0.0
pydantic>=2.5.0,<3.0.0
```

### 3.2 API 服务架构修复

**当前问题**：每次请求创建新的 `TravelAssistant` 实例，导致无状态、开销大

**改进方案**：使用 FastAPI 的依赖注入和单例模式

```python
# src/api/__init__.py
from fastapi import FastAPI, Depends
from src.agents.travel_assistant import TravelAssistant

app = FastAPI()

# 单例模式
_assistant_instance = None

def get_assistant() -> TravelAssistant:
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = TravelAssistant()
    return _assistant_instance

@app.post("/chat")
async def chat(request: ChatRequest, assistant: TravelAssistant = Depends(get_assistant)):
    response = assistant.chat(request.message, request.history)
    return ChatResponse(response=response)
```

### 3.3 公交路线 Bug 修复

**当前问题**：
1. Web 界面中 `city` 参数传递错误
2. 公交路线复用了驾车路线的格式化方法

**修复方案**：

```python
# src/tools/amap/route.py - 添加公交路线格式化方法
@staticmethod
def format_transit_route(data: dict) -> str:
    """格式化公交路线信息"""
    if not data or "route" not in data:
        return "暂无公交路线信息"
    
    route = data["route"]
    transits = route.get("transits", [])
    
    if not transits:
        return "暂无公交路线信息"
    
    result = "🚌 公交路线规划：\n\n"
    for i, transit in enumerate(transits[:3], 1):
        result += f"方案{i}：\n"
        result += f"  预计时间：{transit.get('duration', '未知')}秒\n"
        result += f"  步行距离：{transit.get('walking_distance', '未知')}米\n"
        
        # 解析换乘信息
        segments = transit.get("segments", [])
        transit_lines = []
        for seg in segments:
            if "bus" in seg and seg["bus"]:
                buslines = seg["bus"].get("buslines", [])
                for line in buslines:
                    transit_lines.append(line.get("name", "未知线路"))
        
        if transit_lines:
            result += f"  换乘线路：{' → '.join(transit_lines)}\n"
        result += "\n"
    
    return result
```

```python
# web/app.py - 修复公交路线调用
# 修复前：
data = RouteTool.get_transit_route(route_origin, route_dest, route_dest)

# 修复后：
data = RouteTool.get_transit_route(route_origin, route_dest, city)
if data:
    result = RouteTool.format_transit_route(data)  # 使用公交专用格式化方法
```

## 4. 阶段2：质量提升与测试

### 4.1 Google 代码风格采用

**工具配置**：`pyproject.toml`

```toml
[tool.black]
line-length = 88
target-version = ['py39']

[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

**代码风格改进示例**：

```python
# 改进前
def get_weather(city):
    data = WeatherTool.get_weather(city)
    if data:
        return WeatherTool.format_weather_info(data)
    return "抱歉，暂时无法获取天气信息"

# 改进后 (Google风格)
def get_weather(city: str) -> str:
    """获取指定城市的实时天气信息。
    
    Args:
        city: 城市名称，如"北京"、"上海"。
        
    Returns:
        格式化的天气信息字符串，或错误提示信息。
    """
    data = WeatherTool.get_weather(city)
    if data:
        return WeatherTool.format_weather_info(data)
    return "抱歉，暂时无法获取天气信息"
```

### 4.2 全面测试覆盖

**测试目录结构**：
```
tests/
├── __init__.py
├── conftest.py              # 共享fixtures
├── unit/                    # 单元测试
│   ├── __init__.py
│   ├── test_weather.py
│   ├── test_poi.py
│   ├── test_route.py
│   └── test_tools.py
├── integration/             # 集成测试
│   ├── __init__.py
│   ├── test_agent.py
│   └── test_api.py
└── e2e/                     # 端到端测试
    ├── __init__.py
    └── test_cli.py
```

**单元测试示例**：

```python
# tests/unit/test_weather.py
import pytest
from unittest.mock import Mock, patch
from src.tools.amap.weather import WeatherTool

class TestWeatherTool:
    """天气工具单元测试。"""
    
    @patch('src.tools.amap.weather.requests.get')
    def test_get_weather_success(self, mock_get):
        """测试成功获取天气信息。"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "1",
            "lives": [{
                "city": "北京",
                "weather": "晴",
                "temperature": "25",
                "winddirection": "北"
            }]
        }
        mock_get.return_value = mock_response
        
        result = WeatherTool.get_weather("北京")
        assert result is not None
        assert "北京" in str(result)
    
    @patch('src.tools.amap.weather.requests.get')
    def test_get_weather_failure(self, mock_get):
        """测试获取天气信息失败。"""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "0"}
        mock_get.return_value = mock_response
        
        result = WeatherTool.get_weather("北京")
        assert result is None
```

**集成测试示例**：

```python
# tests/integration/test_agent.py
import pytest
from src.agents.travel_assistant import TravelAssistant

class TestTravelAssistant:
    """旅行助手集成测试。"""
    
    @pytest.fixture
    def assistant(self):
        """创建旅行助手实例。"""
        return TravelAssistant()
    
    def test_basic_chat(self, assistant):
        """测试基本对话功能。"""
        response = assistant.chat("你好")
        assert response is not None
        assert len(response) > 0
    
    def test_weather_query(self, assistant):
        """测试天气查询功能。"""
        response = assistant.chat("北京今天天气怎么样？")
        assert "天气" in response or "晴" in response or "雨" in response
```

### 4.3 统一日志系统

**日志配置**：`src/utils/logger.py`

```python
import logging
import sys
from typing import Optional

def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """设置日志记录器。
    
    Args:
        name: 日志记录器名称。
        level: 日志级别。
        log_file: 日志文件路径（可选）。
        
    Returns:
        配置好的日志记录器。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # 文件处理器（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger

# 全局日志记录器
logger = setup_logger("travel_agent")
```

**使用示例**：

```python
# 改进前
print(f"高德天气API错误: {data.get('info', '未知错误')}")

# 改进后
from src.utils.logger import logger
logger.error(f"高德天气API错误: {data.get('info', '未知错误')}")
```

### 4.4 项目打包配置

**`pyproject.toml` 完整配置**：

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "travel-agent"
version = "1.0.0"
description = "基于LangChain的智能旅行助手"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.9"
dependencies = [
    "langchain>=0.1.0,<1.0.0",
    "langchain-openai>=0.0.5,<1.0.0",
    "langchain-core>=0.1.0,<1.0.0",
    "langgraph>=0.2.0,<1.0.0",
    "fastapi>=0.109.0,<1.0.0",
    "uvicorn>=0.27.0,<1.0.0",
    "streamlit>=1.30.0,<2.0.0",
    "requests>=2.31.0,<3.0.0",
    "python-dotenv>=1.0.0,<2.0.0",
    "pydantic>=2.5.0,<3.0.0",
    "pydantic-settings>=2.0.0,<3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0,<8.0.0",
    "pytest-asyncio>=0.21.0,<1.0.0",
    "black>=23.0.0,<24.0.0",
    "ruff>=0.1.0,<1.0.0",
    "mypy>=1.0.0,<2.0.0",
]

[project.urls]
Homepage = "https://github.com/yourusername/travel-agent"
Documentation = "https://github.com/yourusername/travel-agent#readme"
Repository = "https://github.com/yourusername/travel-agent"
Issues = "https://github.com/yourusername/travel-agent/issues"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]
```

## 5. 阶段3：功能增强与部署

### 5.1 记忆系统实现

**当前问题**：仅保留最近8条消息，进程重启即丢失

**改进方案**：支持多种记忆后端

```python
# src/memory/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseMemory(ABC):
    """记忆系统基类。"""
    
    @abstractmethod
    def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """添加消息到记忆。"""
        pass
    
    @abstractmethod
    def get_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取历史消息。"""
        pass
    
    @abstractmethod
    def clear(self, session_id: str) -> None:
        """清除会话记忆。"""
        pass
```

```python
# src/memory/file_memory.py
import json
from pathlib import Path
from typing import List, Dict, Any
from .base import BaseMemory

class FileMemory(BaseMemory):
    """基于文件的记忆系统。"""
    
    def __init__(self, storage_dir: str = "memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
    
    def _get_file_path(self, session_id: str) -> Path:
        """获取会话文件路径。"""
        return self.storage_dir / f"{session_id}.json"
    
    def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """添加消息到文件记忆。"""
        file_path = self._get_file_path(session_id)
        messages = self.get_messages(session_id)
        messages.append(message)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    
    def get_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取历史消息。"""
        file_path = self._get_file_path(session_id)
        if not file_path.exists():
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            messages = json.load(f)
        
        return messages[-limit:]
    
    def clear(self, session_id: str) -> None:
        """清除会话记忆。"""
        file_path = self._get_file_path(session_id)
        if file_path.exists():
            file_path.unlink()
```

### 5.2 流式响应实现

**改进方案**：使用 Server-Sent Events (SSE)

```python
# src/api/main.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from src.agents.travel_assistant import TravelAssistant
import asyncio

app = FastAPI()

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天接口。"""
    assistant = get_assistant()
    
    async def generate():
        async for chunk in assistant.chat_stream(request.message, request.history):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

```python
# src/agents/travel_assistant.py - 添加流式支持
async def chat_stream(self, user_input: str, chat_history: list = None):
    """流式对话。"""
    messages = self._build_messages(user_input, chat_history)
    
    async for event in self.agent.astream_events({"messages": messages}):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield chunk.content
```

### 5.3 步行路线实现

**当前问题**：定义了 `WALKING_URL` 但未实现

**实现方案**：

```python
# src/tools/amap/route.py - 添加步行路线方法
@staticmethod
def get_walking_route(origin: str, destination: str) -> dict:
    """获取步行路线。
    
    Args:
        origin: 起点坐标（经纬度，格式：经度,纬度）。
        destination: 终点坐标（经纬度，格式：经度,纬度）。
        
    Returns:
        步行路线数据字典。
    """
    params = {
        "key": settings.AMAP_API_KEY,
        "origin": origin,
        "destination": destination,
    }
    
    try:
        response = requests.get(WALKING_URL, params=params, timeout=10)
        data = response.json()
        
        if data.get("status") == "1":
            return data
        else:
            logger.error(f"高德步行路线API错误: {data.get('info', '未知错误')}")
            return None
    except Exception as e:
        logger.error(f"高德步行路线API异常: {str(e)}")
        return None

@staticmethod
def format_walking_route(data: dict) -> str:
    """格式化步行路线信息。"""
    if not data or "route" not in data:
        return "暂无步行路线信息"
    
    route = data["route"]
    paths = route.get("paths", [])
    
    if not paths:
        return "暂无步行路线信息"
    
    path = paths[0]
    distance = int(path.get("distance", 0))
    duration = int(path.get("duration", 0))
    
    # 转换距离和时间
    distance_km = distance / 1000
    duration_min = duration / 60
    
    result = f"🚶 步行路线规划：\n\n"
    result += f"  总距离：{distance_km:.1f}公里\n"
    result += f"  预计时间：{duration_min:.0f}分钟\n\n"
    
    # 步骤详情
    steps = path.get("steps", [])
    if steps:
        result += "  路线详情：\n"
        for i, step in enumerate(steps[:5], 1):
            instruction = step.get("instruction", "")
            step_distance = int(step.get("distance", 0))
            result += f"    {i}. {instruction} ({step_distance}米)\n"
    
    return result
```

### 5.4 Docker 部署支持

**Dockerfile**：

```dockerfile
# 使用官方Python镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONPATH=/app

# 启动命令
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml**：

```yaml
version: '3.8'

services:
  travel-agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ZHIPUAI_API_KEY=${ZHIPUAI_API_KEY}
      - AMAP_API_KEY=${AMAP_API_KEY}
    volumes:
      - .env:/app/.env
      - memory:/app/memory
    restart: unless-stopped

  streamlit:
    build: .
    command: streamlit run web/app.py --server.port=8501 --server.address=0.0.0.0
    ports:
      - "8501:8501"
    environment:
      - ZHIPUAI_API_KEY=${ZHIPUAI_API_KEY}
      - AMAP_API_KEY=${AMAP_API_KEY}
    volumes:
      - .env:/app/.env
      - memory:/app/memory
    restart: unless-stopped

volumes:
  memory:
```

## 6. 实施计划

### 6.1 阶段1：核心缺陷修复（第1-2周）

**任务清单**：
1. 修复 `requirements.txt` 依赖问题
2. 重构 API 服务架构，使用单例模式
3. 修复公交路线 Bug
4. 改进配置管理，使用 Pydantic BaseSettings

**验收标准**：
- 项目可以正常安装和运行
- API 服务支持有状态对话
- 公交路线功能正常工作

### 6.2 阶段2：质量提升与测试（第3-4周）

**任务清单**：
1. 配置 Google 代码风格工具（black, ruff, mypy）
2. 重构现有代码，采用 Google 风格
3. 创建测试目录结构
4. 编写单元测试和集成测试
5. 实现统一日志系统
6. 完善 `pyproject.toml` 打包配置

**验收标准**：
- 代码通过所有风格检查
- 测试覆盖率达到 80% 以上
- 日志系统统一且规范
- 项目可以通过 `pip install -e .` 安装

### 6.3 阶段3：功能增强与部署（第5-6周）

**任务清单**：
1. 实现记忆系统基类和文件记忆实现
2. 修改 TravelAssistant 支持记忆系统
3. 实现流式响应接口
4. 实现步行路线功能
5. 创建 Dockerfile 和 docker-compose.yml
6. 更新 README 文档

**验收标准**：
- 记忆系统可以正常保存和加载历史
- 流式响应功能正常工作
- 步行路线查询功能完整
- Docker 部署可以正常运行

## 7. 风险评估

### 7.1 技术风险

- **依赖兼容性**：新依赖版本可能与现有代码不兼容
  - 缓解措施：使用版本上限，充分测试
- **API 变更**：高德地图 API 可能发生变更
  - 缓解措施：添加错误处理和日志记录

### 7.2 时间风险

- **测试覆盖率不足**：可能无法在预定时间内达到 80% 覆盖率
  - 缓解措施：优先测试核心功能，逐步提升覆盖率
- **功能实现复杂度**：流式响应和记忆系统可能比预期复杂
  - 缓解措施：分阶段实现，先实现基础功能

## 8. 成功标准

### 8.1 功能完整性

- 所有核心功能正常工作
- 新增功能按预期运行
- 测试覆盖率达到 80% 以上

### 8.2 代码质量

- 代码风格符合 Google 规范
- 日志系统统一且规范
- 项目结构清晰，易于维护

### 8.3 部署能力

- 项目可以通过 `pip install -e .` 安装
- Docker 部署可以正常运行
- 提供完整的使用文档

## 9. 附录

### 9.1 相关文档

- [项目架构文档](../architecture.md)
- [高德地图 API 文档](https://lbs.amap.com/api/webservice/guide/api/weather)
- [LangChain 文档](https://python.langchain.com/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)

### 9.2 工具和依赖

- Python 3.9+
- LangChain 0.1.0+
- LangGraph 0.2.0+
- FastAPI 0.109.0+
- Streamlit 1.30.0+
- Pydantic 2.5.0+
- pytest 7.0.0+
- black 23.0.0+
- ruff 0.1.0+
- mypy 1.0.0+
