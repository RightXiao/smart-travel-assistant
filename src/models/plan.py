"""行程结构化输出契约。

与普通聊天的自由文本不同，行程规划（``POST /plan``）通过
``llm.with_structured_output`` 强制 LLM 输出符合本模块 schema 的 JSON，
使下游可以做**确定性校验**（预算算术、景点名锚定），而非信任自由文本。
"""
from pydantic import BaseModel, Field


class TripRequestArgs(BaseModel):
    """从自然语言抽取的行程参数（Plan 阶段第一步）。"""

    destination: str = Field(default="", description="目的地城市，如：北京；未提及留空")
    days: int = Field(default=1, ge=1, le=15, description="行程天数，未提及默认 1")
    budget: int = Field(default=0, ge=0, description="总预算（元），未提及为 0")


class DayPlan(BaseModel):
    """单日行程。"""

    day: int = Field(ge=1, description="第几天（从 1 开始）")
    title: str = Field(default="", description="当日主题，如：历史文化线")
    spots: list[str] = Field(
        default_factory=list,
        description="当日游览景点（只能使用给定景点池中的名称）",
    )
    estimated_cost: int = Field(default=0, ge=0, description="当日预计花费（元，含门票/市内交通/餐饮）")


class TravelPlan(BaseModel):
    """完整行程方案（结构化输出目标 schema）。"""

    destination: str = Field(description="目的地城市")
    days: int = Field(ge=1, description="行程天数")
    day_plans: list[DayPlan] = Field(default_factory=list, description="逐日安排")
    hotel_preference: str = Field(default="", description="住宿区域/档位建议")
    hotel_est_cost_total: int = Field(default=0, ge=0, description="住宿总预算估算（元）")
    food_recommendations: list[str] = Field(
        default_factory=list, description="美食推荐（来自美食查询结果）"
    )
    total_estimated_cost: int = Field(
        default=0, ge=0, description="总预算估算（元），必须等于各日花费与住宿之和"
    )
    general_tips: str = Field(default="", description="交通/门票/注意事项")
