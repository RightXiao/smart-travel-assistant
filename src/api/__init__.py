"""FastAPI 应用 — 使用 ``uvicorn src.api.main:app`` 启动。

约定：
- 成功响应：HTTP 200 + ``{"status": "ok", ...}``；
- 上游（高德 / LLM）失败：HTTP 502 + ``{"status": "error", "message": ...}``；
- 客户端参数错误（定位失败、校验失败）：HTTP 400 / 422；
- 可选鉴权：设置环境变量 ``API_AUTH_TOKEN`` 后，所有端点要求
  ``Authorization: Bearer <token>``（未设置时不启用，便于本地开发）；
- 流式对话：``POST /chat/stream`` 以 SSE（``text/event-stream``）逐步返回
  ``{"type": "tool_start"|"token"|"final"|"error", ...}`` 事件。
"""
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.config.settings import LLM_PRESETS, get_settings, resolve_llm_config
from src.models.travel import (
    ChatRequest,
    ChatResponse,
    MultiSpotRouteRequest,
    PlanRequest,
)
from src.tools.amap.route import RouteResolutionError
from src.utils.logger import logger

# ---------------------------------------------------------------------------
# 可选鉴权：设置 API_AUTH_TOKEN 后，所有端点要求 Bearer Token
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    """可选 Bearer 鉴权：未配置 ``API_AUTH_TOKEN`` 时放行。"""
    token = get_settings().API_AUTH_TOKEN
    if not token:
        return
    if credentials is None or credentials.credentials != token:
        raise HTTPException(status_code=401, detail="未授权：缺少或无效的 Bearer Token")


app = FastAPI(
    title="智能旅行助手 API",
    description="基于 LangChain + GLM + 高德地图的智能旅行助手 RESTful API",
    version=__version__,
    dependencies=[Depends(require_auth)],
)

# 单例管理器（FastAPI 同步端点运行在线程池中，需加锁避免并发重复初始化）
_assistant_instance = None
_assistant_lock = threading.Lock()


def get_assistant():
    """获取 TravelAssistant 单例实例（双重检查加锁）。"""
    global _assistant_instance
    if _assistant_instance is None:
        with _assistant_lock:
            if _assistant_instance is None:
                from src.agents.travel_assistant import TravelAssistant

                _assistant_instance = TravelAssistant()
    return _assistant_instance


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """访问日志 + 请求追踪：为每个请求分配 ``X-Request-ID`` 并记录耗时。"""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "请求处理异常 %s %s [req=%s]",
            request.method,
            request.url.path,
            request_id,
        )
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %s (%.1fms) [req=%s]",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response


def _error(message: str, status_code: int = 502) -> JSONResponse:
    """统一错误响应体（与成功响应的 ``status`` 字段约定保持一致）。"""
    return JSONResponse(
        status_code=status_code, content={"status": "error", "message": message}
    )


@app.get("/")
def root(request: Request):
    """API 信息；浏览器访问（``Accept: text/html``）时跳转到全新 Web 前端 ``/web/``。

    curl / 健康检查 / 压测等非浏览器请求（默认 ``Accept: */*``）不受影响，
    仍返回 JSON —— 根端点 200 JSON 契约保持不变。
    """
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(url="/web/", status_code=307)
    return {
        "name": "智能旅行助手 API",
        "version": __version__,
        "status": "running",
        "web": "/web/",
    }


@app.get("/config/llm")
def get_llm_config():
    """当前多厂商 LLM 接入配置（密钥脱敏）。

    返回生效的厂商 / 模型 / 端点，以及全部厂商预设（预设不含任何密钥，
    可安全展示），供前端展示「当前由哪家模型服务」并提供切换指引。
    切换厂商通过服务端环境变量完成（``LLM_PROVIDER`` / ``LLM_API_KEY`` /
    ``LLM_MODEL``），运行时只读。
    """
    try:
        cfg = resolve_llm_config()
    except ValueError as e:
        # provider 配置错误属服务端配置问题，返回 500 + 明确原因
        return _error(str(e), status_code=500)
    key = cfg["api_key"]
    masked = key[:4] + "****" + key[-4:] if len(key) > 12 else ("已配置" if key else "未配置")
    return {
        "status": "ok",
        "data": {
            "provider": cfg["provider"],
            "model": cfg["model"],
            "base_url": cfg["base_url"],
            "api_key": masked,
            "presets": {
                name: {"base_url": p["base_url"], "default_model": p["default_model"]}
                for name, p in LLM_PRESETS.items()
            },
        },
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, assistant=Depends(get_assistant)):
    """对话（异步：LangGraph ``ainvoke``，工具调用在执行器线程中运行）。"""
    history_dicts = [m.model_dump() for m in request.chat_history]
    response_text = await assistant.achat(request.message, chat_history=history_dicts)
    return ChatResponse(response=response_text)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, assistant=Depends(get_assistant)):
    """流式对话（SSE）。

    事件流格式（``data: <json>\\n\\n``）::

        {"type": "tool_start", "name": "查询实时天气"}
        {"type": "token", "content": "..."}
        {"type": "final", "content": "完整回复"}
        data: [DONE]
    """
    history_dicts = [m.model_dump() for m in request.chat_history]

    async def event_stream():
        try:
            async for event in assistant.astream_chat(
                request.message, chat_history=history_dicts
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:  # 流中异常也要以 error 事件收尾，避免客户端悬挂
            logger.error("SSE 流异常: %s", e, exc_info=True)
            yield "data: " + json.dumps(
                {"type": "error", "message": "流式响应中断，请重试。"},
                ensure_ascii=False,
            ) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/weather/{city}")
async def get_weather(city: str, forecast: bool = False):
    from src.tools.amap.weather import WeatherTool

    if forecast:
        data = await WeatherTool.aget_weather_forecast(city)
        if data:
            return {"status": "ok", "data": WeatherTool.format_forecast_info(data)}
    else:
        data = await WeatherTool.aget_weather(city)
        if data:
            weather_info = WeatherTool.format_weather_info(data)
            dressing = WeatherTool.get_dressing_advice(data)
            return {
                "status": "ok",
                "data": {"weather": weather_info, "dressing_advice": dressing},
            }
    return _error("无法查询天气信息")


@app.get("/spots/{city}")
async def get_spots(city: str, page_size: int = Query(10, ge=1, le=25)):
    from src.tools.amap.poi import POITool

    data = await POITool.asearch_scenic_spots(city, page_size=page_size)
    if data and "pois" in data:
        return {"status": "ok", "count": len(data["pois"]), "data": data["pois"]}
    return _error("无法查询景点信息")


@app.get("/food/{city}")
async def get_food(city: str, page_size: int = Query(10, ge=1, le=25)):
    from src.tools.amap.poi import POITool

    data = await POITool.asearch_food(city, page_size=page_size)
    if data and "pois" in data:
        return {"status": "ok", "count": len(data["pois"]), "data": data["pois"]}
    return _error("无法查询美食信息")


@app.get("/hotels/{city}")
async def get_hotels(
    city: str, budget: Optional[str] = None, page_size: int = Query(10, ge=1, le=25)
):
    from src.tools.amap.poi import POITool

    if budget:
        data = await POITool.asearch_hotel_by_budget(city, budget, page_size=page_size)
    else:
        data = await POITool.asearch_hotel(city, page_size=page_size)
    if data and "pois" in data:
        return {"status": "ok", "count": len(data["pois"]), "data": data["pois"]}
    return _error("无法查询住宿信息")


@app.get("/route/driving")
async def get_driving_route(origin: str, destination: str):
    from src.tools.amap.route import RouteTool

    try:
        data = await RouteTool.aget_driving_route(origin, destination)
    except RouteResolutionError as e:
        return _error(str(e), status_code=400)
    if data and "route" in data:
        return {"status": "ok", "data": RouteTool.format_driving_route(data)}
    return _error("无法查询驾车路线")


@app.get("/route/transit")
async def get_transit_route(origin: str, destination: str, city: str):
    from src.tools.amap.route import RouteTool

    try:
        data = await RouteTool.aget_transit_route(origin, destination, city)
    except RouteResolutionError as e:
        return _error(str(e), status_code=400)
    if data and "route" in data:
        return {"status": "ok", "data": RouteTool.format_transit_route(data)}
    return _error("无法查询公交路线")


@app.post("/route/multi-spot")
def plan_multi_spot_route(request: MultiSpotRouteRequest):
    from src.tools.amap.route import RouteTool

    data = RouteTool.plan_multi_spot_route(
        request.spots,
        city=request.city,
        mode=request.mode,
        optimize_order=request.optimize_order,
    )
    if data and not data.get("error"):
        return {"status": "ok", "data": RouteTool.format_multi_spot_route(data)}
    message = (data or {}).get("error") or "无法规划多景点路线"
    return _error(message, status_code=400)


@app.post("/plan")
def create_plan(request: PlanRequest, assistant=Depends(get_assistant)):
    """结构化行程规划（Plan-and-Execute）。

    流程：参数抽取（结构化）→ 高德景点池 → 地理就近逐日排程 → ReAct 调研
    → ``TravelPlan`` 结构化草稿 → Verifier 校验（预算算术/景点锚定），
    未通过时自动带 issues 自纠重试（``PLAN_VERIFY_RETRIES``，默认 1 次）。

    响应 ``data`` 字段：``plan``（结构化行程）、``verification``（校验结果，
    含 issues/warnings）、``schedule``（确定性逐日排程）、``params``（抽取参数）、
    ``budget_floor``（确定性预算下限）。
    """
    try:
        result = assistant.plan_trip(request.message, session_id=request.session_id)
    except Exception as e:
        logger.error("行程规划失败: %s", e, exc_info=True)
        return _error("行程规划失败，请稍后重试或调整需求描述")

    return {
        "status": "ok",
        "data": {
            "plan": result["plan"].model_dump(),
            "verification": result["verification"].model_dump(),
            "schedule": [d.model_dump() for d in result["schedule"]],
            "params": result["params"].model_dump(),
            "budget_floor": result["budget_floor"].model_dump(),
        },
    }


# ---------------------------------------------------------------------------
# 全新 Web 前端（零构建静态 SPA）：挂载在 /web
# 访问 http://127.0.0.1:8000/web/ 即可使用攻略定制界面。
# 说明：StaticFiles 挂载不继承 app 级鉴权依赖 —— 静态资源不含敏感数据，
#       页面内 API 调用仍受 ``require_auth`` 保护（Token 在页面设置中配置）。
# ---------------------------------------------------------------------------
_WEB_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "static"
if _WEB_STATIC_DIR.is_dir():
    app.mount(
        "/web",
        StaticFiles(directory=str(_WEB_STATIC_DIR), html=True),
        name="web",
    )
