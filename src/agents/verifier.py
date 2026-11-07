"""行程草稿校验器（Verifier）。

对 ``with_structured_output`` 产出的 :class:`TravelPlan` 做**确定性校验**：

- **预算算术一致性**：各日花费 + 住宿合计 必须等于 总预算估算（容忍 1 元舍入差）；
- **景点名事实锚定**：行程中的景点必须出现在景点 API 查询结果中
  （幻觉防护；景点池为空时降级为告警，不阻断）；
- **预算上限**：总估算超出用户预算时给出告警（不视为失败，由用户裁决）。

校验失败时把 ``issues`` 回喂给结构化生成做一轮**自纠**（见
``TravelAssistant.plan_trip``）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.plan import TravelPlan

# 预算算术容忍误差（元）——各分为 int，正常应精确相等，容忍 1 元舍入
COST_TOLERANCE = 1


class VerificationResult(BaseModel):
    """校验结果。"""

    ok: bool = Field(description="是否通过（无 issue 即通过）")
    issues: list[str] = Field(default_factory=list, description="必须修正的问题")
    warnings: list[str] = Field(default_factory=list, description="提示性告警")
    over_budget: bool = Field(default=False, description="总估算是否超出用户预算")


def verify_plan(
    plan: TravelPlan,
    allowed_spots: list[str] | None = None,
    budget: int = 0,
) -> VerificationResult:
    """校验行程草稿，返回结构化结果。

    Args:
        plan: 待校验的结构化行程。
        allowed_spots: 景点 API 返回的景点名白名单；为空列表/None 时
            跳过锚定并记告警（API 失败不应阻断规划）。
        budget: 用户总预算（元），0 表示未提供。
    """
    issues: list[str] = []
    warnings: list[str] = []

    # 1) 天数与逐日安排一致性
    if plan.day_plans and len(plan.day_plans) != plan.days:
        warnings.append(f"行程天数为 {plan.days} 天，但逐日安排有 {len(plan.day_plans)} 天")

    # 2) 预算算术一致性
    days_sum = sum(d.estimated_cost for d in plan.day_plans)
    expected_total = days_sum + plan.hotel_est_cost_total
    if abs(expected_total - plan.total_estimated_cost) > COST_TOLERANCE:
        issues.append(
            f"预算算术不一致：各日合计 {days_sum} 元 + 住宿 {plan.hotel_est_cost_total} 元"
            f" ≠ 总计 {plan.total_estimated_cost} 元，请修正 total_estimated_cost"
        )

    # 3) 景点名事实锚定（幻觉防护）
    if allowed_spots:
        whitelist = set(allowed_spots)
        hallucinated = sorted(
            {
                spot
                for d in plan.day_plans
                for spot in d.spots
                if spot and spot not in whitelist
            }
        )
        for spot in hallucinated:
            issues.append(f"景点「{spot}」未出现在景点查询结果中，疑似编造，请替换或删除")
    else:
        warnings.append("景点查询结果为空，已跳过景点名事实锚定校验")

    # 4) 预算上限（告警不阻断）
    over_budget = budget > 0 and plan.total_estimated_cost > budget
    if over_budget:
        warnings.append(
            f"总预算估算 {plan.total_estimated_cost} 元超出用户预算 {budget} 元，" "建议说明原因或给出压缩方案"
        )

    return VerificationResult(
        ok=not issues, issues=issues, warnings=warnings, over_budget=over_budget
    )
