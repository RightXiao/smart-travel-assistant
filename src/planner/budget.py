"""预算闭环：确定性费用拆分估算。

行程规划中「餐饮 + 市内交通」部分由本模块**确定性估算**（不经 LLM），
作为预算下限注入结构化生成 prompt，让 LLM 的总预算估算有事实锚点；
住宿/门票等不可确定的部分由 LLM 依据工具查询结果估算，最终由
Verifier 做算术一致性与预算上限校验（见 ``src/agents/verifier.py``）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# 默认经验参数（可在调用方覆写）
DEFAULT_DAILY_FOOD = 150.0  # 人均每日餐饮（元）
DEFAULT_TRANSIT_RATE_PER_KM = 2.5  # 市内交通每公里（元，打车/公交混合粗估）


class BudgetBreakdown(BaseModel):
    """预算拆分（元）。"""

    hotel_total: float = Field(default=0.0, ge=0, description="住宿合计")
    food_total: float = Field(default=0.0, ge=0, description="餐饮合计")
    transit_total: float = Field(default=0.0, ge=0, description="市内交通合计")
    tickets_total: float = Field(default=0.0, ge=0, description="门票合计")
    total: float = Field(default=0.0, ge=0, description="合计")


def estimate_budget(
    days: int,
    hotel_cost_per_night: float = 0.0,
    transit_km_total: float = 0.0,
    daily_food: float = DEFAULT_DAILY_FOOD,
    transit_rate_per_km: float = DEFAULT_TRANSIT_RATE_PER_KM,
    tickets_total: float = 0.0,
    nights: int | None = None,
) -> BudgetBreakdown:
    """确定性估算行程预算拆分。

    Args:
        days: 行程天数。
        hotel_cost_per_night: 每晚住宿参考价（来自酒店查询，未知传 0）。
        transit_km_total: 市内移动总距离（公里，来自逐日排程估算）。
        daily_food: 人均每日餐饮。
        transit_rate_per_km: 市内交通每公里成本。
        tickets_total: 门票合计（未知传 0）。
        nights: 住宿晚数（默认 ``days - 1``）。
    """
    days = max(int(days or 1), 1)
    if nights is None:
        nights = max(days - 1, 0)

    hotel_total = round(max(hotel_cost_per_night, 0.0) * max(nights, 0), 2)
    food_total = round(max(daily_food, 0.0) * days, 2)
    transit_total = round(max(transit_km_total, 0.0) * max(transit_rate_per_km, 0.0), 2)
    tickets_total = round(max(tickets_total, 0.0), 2)
    total = round(hotel_total + food_total + transit_total + tickets_total, 2)
    return BudgetBreakdown(
        hotel_total=hotel_total,
        food_total=food_total,
        transit_total=transit_total,
        tickets_total=tickets_total,
        total=total,
    )
