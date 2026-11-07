"""Plan-and-Execute 行程规划管线测试（LLM/POI 全 mock）。"""
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.travel_assistant import TravelAssistant
from src.memory.file_memory import FileMemory
from src.models.plan import DayPlan, TravelPlan, TripRequestArgs

_TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp"

_POIS = {
    "status": "1",
    "pois": [
        {"name": "西湖", "location": "120.14,30.25"},
        {"name": "灵隐寺", "location": "120.10,30.24"},
        {"name": "宋城", "location": "120.12,30.19"},
    ],
}


@pytest.fixture
def mem_dir():
    _TMP_ROOT.mkdir(exist_ok=True)
    d = Path(_TMP_ROOT) / f"plan_{id(object())}"
    yield d
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def _build(mem_dir):
    with patch("src.agents.travel_assistant.require_api_keys"), patch(
        "src.agents.travel_assistant.build_chat_model"
    ), patch("src.agents.travel_assistant.create_react_agent"):
        return TravelAssistant(memory=FileMemory(storage_dir=str(mem_dir)))


def _good_plan(**overrides):
    base = dict(
        destination="杭州",
        days=2,
        day_plans=[
            DayPlan(day=1, spots=["西湖", "灵隐寺"], estimated_cost=300),
            DayPlan(day=2, spots=["宋城"], estimated_cost=200),
        ],
        hotel_est_cost_total=500,
        total_estimated_cost=1000,
    )
    base.update(overrides)
    return TravelPlan(**base)


class _StructuredFake:
    """模拟 ``llm.with_structured_output(schema)``：按调用序返回预设值。"""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestPlanTrip:
    def test_happy_path(self, mem_dir):
        asst = _build(mem_dir)
        extractor = _StructuredFake(
            [TripRequestArgs(destination="杭州", days=2, budget=2000)]
        )
        planner = _StructuredFake([_good_plan()])
        asst.llm = MagicMock()
        asst.llm.with_structured_output.side_effect = [extractor, planner]
        asst.chat = MagicMock(return_value="调研材料：西湖、美食、酒店信息")

        with patch(
            "src.tools.amap.poi.POITool.search_scenic_spots", return_value=_POIS
        ):
            result = asst.plan_trip("杭州2天预算2000", session_id="s1")

        assert result["params"].destination == "杭州"
        assert result["verification"].ok is True
        # 排程骨架来自真实 POI 坐标（3 景点 2 天）
        assert sum(len(d.spots) for d in result["schedule"]) == 3
        # 预算下限为确定性估算（餐饮 300 + 交通）
        assert result["budget_floor"].food_total == 300
        # 调研材料进入结构化 prompt
        planner_prompt = str(planner.calls[0])
        assert "调研材料" in planner_prompt
        assert "西湖" in planner_prompt  # 排程骨架注入

    def test_hallucination_triggers_retry_then_passes(self, mem_dir):
        asst = _build(mem_dir)
        extractor = _StructuredFake(
            [TripRequestArgs(destination="杭州", days=2, budget=0)]
        )
        bad = _good_plan(
            day_plans=[
                DayPlan(day=1, spots=["编造景点"], estimated_cost=300),
                DayPlan(day=2, spots=["宋城"], estimated_cost=200),
            ],
            total_estimated_cost=1000,
        )
        planner = _StructuredFake([bad, _good_plan()])
        asst.llm = MagicMock()
        asst.llm.with_structured_output.side_effect = [extractor, planner]
        asst.chat = MagicMock(return_value="调研")

        with patch(
            "src.tools.amap.poi.POITool.search_scenic_spots", return_value=_POIS
        ):
            result = asst.plan_trip("杭州2天", session_id="s1")

        # 首稿含编造景点 → 校验失败 → 自纠一次后通过
        assert planner.calls[0] is not None
        assert len(planner.calls) == 2
        assert "编造景点" in str(planner.calls[1])  # issues 回喂
        assert result["verification"].ok is True

    def test_retry_budget_exhausted_returns_last_verification(self, mem_dir):
        asst = _build(mem_dir)
        extractor = _StructuredFake(
            [TripRequestArgs(destination="杭州", days=2, budget=0)]
        )
        bad = _good_plan(total_estimated_cost=998)  # 算术不一致（差 2 元）
        planner = _StructuredFake([bad, bad])  # 重试后仍错
        asst.llm = MagicMock()
        asst.llm.with_structured_output.side_effect = [extractor, planner]
        asst.chat = MagicMock(return_value="调研")

        with patch(
            "src.tools.amap.poi.POITool.search_scenic_spots", return_value=_POIS
        ):
            result = asst.plan_trip("杭州2天", session_id="s1")

        # PLAN_VERIFY_RETRIES 默认 1：初稿 + 1 次自纠 = 2 次生成
        assert len(planner.calls) == 2
        assert result["verification"].ok is False
        assert any("预算算术不一致" in i for i in result["verification"].issues)

    def test_poi_failure_degrades_to_warning(self, mem_dir):
        """景点 API 失败时跳过锚定（告警）而非阻断规划。"""
        asst = _build(mem_dir)
        extractor = _StructuredFake(
            [TripRequestArgs(destination="杭州", days=1, budget=0)]
        )
        plan = _good_plan(
            days=1,
            day_plans=[DayPlan(day=1, spots=["任意"], estimated_cost=1500)],
            total_estimated_cost=2000,
        )
        planner = _StructuredFake([plan])
        asst.llm = MagicMock()
        asst.llm.with_structured_output.side_effect = [extractor, planner]
        asst.chat = MagicMock(return_value="调研")

        with patch("src.tools.amap.poi.POITool.search_scenic_spots", return_value=None):
            result = asst.plan_trip("杭州1天", session_id="s1")

        assert result["verification"].ok is True
        assert any("跳过景点名事实锚定" in w for w in result["verification"].warnings)
        assert result["schedule"] == []

    def test_extraction_failure_propagates(self, mem_dir):
        asst = _build(mem_dir)
        extractor = _StructuredFake([RuntimeError("llm down")])
        asst.llm = MagicMock()
        asst.llm.with_structured_output.return_value = extractor

        with patch(
            "src.tools.amap.poi.POITool.search_scenic_spots", return_value=_POIS
        ):
            with pytest.raises(RuntimeError):
                asst.plan_trip("杭州2天", session_id="s1")
