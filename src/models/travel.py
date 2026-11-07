"""API 请求 / 响应模型。

仅保留当前 API 实际接线的契约模型并施加输入约束（长度上限、role 白名单、
mode 枚举），在进入业务逻辑前拦截非法输入。
"""
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="用户消息")
    chat_history: list[ChatMessage] = Field(default_factory=list)


class MultiSpotRouteRequest(BaseModel):
    spots: list[str] = Field(min_length=2, description="景点名称列表（至少 2 个）")
    city: str = ""
    mode: Literal["driving", "transit"] = "driving"
    optimize_order: bool = Field(default=False, description="是否按地理位置就近重排景点顺序以减少绕路")


class ChatResponse(BaseModel):
    response: str


class PlanRequest(BaseModel):
    """行程规划请求（Plan-and-Execute 管线入口）。"""

    message: str = Field(min_length=1, max_length=2000, description="行程需求描述")
    session_id: str = Field(default="default", max_length=128, description="会话标识")
