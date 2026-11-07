"""确定性排程与预算拆分引擎测试。"""
from src.planner.budget import estimate_budget
from src.planner.itinerary import build_day_schedule


class TestBuildDaySchedule:
    def test_even_split_in_proximity_order(self):
        # 同一条经线上的 4 个点：A(0) B(0.1) C(10) D(10.1)
        named = [
            ("A", "116.0,0.0"),
            ("C", "116.0,10.0"),
            ("B", "116.0,0.1"),
            ("D", "116.0,10.1"),
        ]
        schedule = build_day_schedule(named, days=2)
        assert len(schedule) == 2
        # 就近排序后为 A B C D；连续切块 → Day1=[A,B] Day2=[C,D]
        assert schedule[0].spots == ["A", "B"]
        assert schedule[1].spots == ["C", "D"]
        assert schedule[0].day == 1 and schedule[1].day == 2
        # 每日距离为段内 haversine 之和（A→B ≈ 11.1km）
        assert 10 < schedule[0].est_distance_km < 13

    def test_more_days_than_spots(self):
        named = [("A", "116.0,0.0"), ("B", "116.0,0.1")]
        schedule = build_day_schedule(named, days=5)
        assert len(schedule) == 2  # 不生成空天数
        assert schedule[0].spots == ["A"]
        assert schedule[1].spots == ["B"]

    def test_single_spot_single_day(self):
        schedule = build_day_schedule([("A", "116.0,0.0")], days=3)
        assert len(schedule) == 1
        assert schedule[0].spots == ["A"]
        assert schedule[0].est_distance_km == 0.0

    def test_empty_input(self):
        assert build_day_schedule([], days=2) == []

    def test_unparseable_coord_distance_zero(self):
        named = [("A", "bad"), ("B", "also-bad")]
        schedule = build_day_schedule(named, days=1)
        assert schedule[0].spots == ["A", "B"]
        assert schedule[0].est_distance_km == 0.0

    def test_days_clamped_to_at_least_one(self):
        schedule = build_day_schedule([("A", "116.0,0.0")], days=0)
        assert len(schedule) == 1


class TestEstimateBudget:
    def test_basic_breakdown(self):
        b = estimate_budget(days=3, hotel_cost_per_night=400, transit_km_total=20)
        # 住宿 400×2 晚 + 餐饮 150×3 + 交通 20×2.5
        assert b.hotel_total == 800
        assert b.food_total == 450
        assert b.transit_total == 50
        assert b.total == 1300

    def test_nights_override(self):
        b = estimate_budget(days=2, hotel_cost_per_night=300, nights=2)
        assert b.hotel_total == 600

    def test_negative_inputs_clamped(self):
        b = estimate_budget(days=2, hotel_cost_per_night=-5, transit_km_total=-1)
        assert b.hotel_total == 0
        assert b.transit_total == 0
        assert b.total == 300  # 仅餐饮

    def test_days_minimum_one(self):
        b = estimate_budget(days=0)
        assert b.food_total == 150
