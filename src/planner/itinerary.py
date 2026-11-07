"""行程逐日排程引擎（确定性，不依赖 LLM）。

输入带坐标的景点池，输出逐日安排：
1. 复用路线模块的最近邻贪心排序，把地理上相邻的景点排在一起；
2. 按天数**连续切块**（相邻景点落在同一天，避免同一天横跨城区两端）；
3. 估算每日市内移动距离（haversine 逐段累加）。

该排程作为「骨架」注入结构化生成 prompt（Plan-and-Execute 的 Plan 产物），
LLM 负责在此骨架上补充主题/花费/贴士（Execute）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.tools.amap.geo import haversine_km, parse_coord
from src.tools.amap.route import order_spots_by_proximity


class DaySchedule(BaseModel):
    """单日排程骨架。"""

    day: int = Field(ge=1, description="第几天")
    spots: list[str] = Field(default_factory=list, description="当日景点（就近顺序）")
    est_distance_km: float = Field(
        default=0.0, ge=0, description="当日市内移动距离估算（公里，直线距离累加）"
    )


def build_day_schedule(
    named_coords: list[tuple[str, str]], days: int
) -> list[DaySchedule]:
    """把 ``(景点名, 坐标)`` 列表切分为 ``days`` 天的排程。

    - 景点少于 2 个时全部放进第 1 天；
    - ``days`` 大于景点数时只产出景点数个非空日（不生成空天数）；
    - 坐标无法解析的景点按原相对顺序追加到末尾参与切块（距离按 0 计）。
    """
    days = max(int(days or 1), 1)
    if not named_coords:
        return []

    names = [name for name, _ in named_coords]
    coords = [coord for _, coord in named_coords]
    if len(names) > 1:
        names, coords = order_spots_by_proximity(names, coords)

    effective_days = min(days, len(names))
    base, rem = divmod(len(names), effective_days)

    schedules: list[DaySchedule] = []
    idx = 0
    for day in range(1, effective_days + 1):
        size = base + (1 if day <= rem else 0)
        chunk_names = names[idx : idx + size]
        chunk_coords = coords[idx : idx + size]
        idx += size

        distance = 0.0
        for i in range(len(chunk_coords) - 1):
            a, b = parse_coord(chunk_coords[i]), parse_coord(chunk_coords[i + 1])
            if a is not None and b is not None:
                distance += haversine_km(a, b)

        schedules.append(
            DaySchedule(
                day=day,
                spots=chunk_names,
                est_distance_km=round(distance, 1),
            )
        )
    return schedules
