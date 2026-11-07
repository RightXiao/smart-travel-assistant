"""行程草稿校验器测试。"""
from src.agents.verifier import verify_plan
from src.models.plan import DayPlan, TravelPlan


def _plan(**overrides):
    base = dict(
        destination="杭州",
        days=2,
        day_plans=[
            DayPlan(day=1, spots=["西湖"], estimated_cost=300),
            DayPlan(day=2, spots=["灵隐寺"], estimated_cost=200),
        ],
        hotel_est_cost_total=500,
        total_estimated_cost=1000,
    )
    base.update(overrides)
    return TravelPlan(**base)


class TestVerifyPlan:
    def test_ok_plan_passes(self):
        result = verify_plan(_plan(), allowed_spots=["西湖", "灵隐寺"], budget=2000)
        assert result.ok is True
        assert result.issues == []
        assert result.over_budget is False

    def test_arithmetic_mismatch_is_issue(self):
        plan = _plan(total_estimated_cost=998)  # 应为 300+200+500=1000，差 2 元超容忍
        result = verify_plan(plan, allowed_spots=["西湖", "灵隐寺"])
        assert result.ok is False
        assert any("预算算术不一致" in i for i in result.issues)

    def test_arithmetic_within_tolerance_passes(self):
        plan = _plan(total_estimated_cost=1001)  # 1 元舍入差
        result = verify_plan(plan, allowed_spots=["西湖", "灵隐寺"])
        assert result.ok is True

    def test_hallucinated_spot_is_issue(self):
        plan = _plan(
            day_plans=[
                DayPlan(day=1, spots=["西湖", "编造景点"], estimated_cost=300),
                DayPlan(day=2, spots=["灵隐寺"], estimated_cost=200),
            ],
            total_estimated_cost=1000,
        )
        result = verify_plan(plan, allowed_spots=["西湖", "灵隐寺"])
        assert result.ok is False
        assert any("编造景点" in i and "疑似编造" in i for i in result.issues)
        # 真实景点不应被误报
        assert not any("西湖" in i for i in result.issues)

    def test_empty_spot_pool_skips_anchoring_with_warning(self):
        """景点池为空（API 失败）时降级为告警，不阻断规划。"""
        result = verify_plan(_plan(), allowed_spots=[])
        assert result.ok is True
        assert any("跳过景点名事实锚定" in w for w in result.warnings)

    def test_over_budget_is_warning_not_issue(self):
        result = verify_plan(_plan(), allowed_spots=["西湖", "灵隐寺"], budget=800)
        assert result.ok is True
        assert result.over_budget is True
        assert any("超出用户预算" in w for w in result.warnings)

    def test_day_count_mismatch_is_warning(self):
        plan = _plan(days=3)
        result = verify_plan(plan, allowed_spots=["西湖", "灵隐寺"])
        assert result.ok is True
        assert any("逐日安排" in w for w in result.warnings)

    def test_no_budget_no_over_budget_warning(self):
        result = verify_plan(_plan(), allowed_spots=["西湖", "灵隐寺"], budget=0)
        assert result.over_budget is False
        assert result.warnings == [""] or all("预算" not in w for w in result.warnings)
