"""评估套件 pytest 集成：标记为 ``eval``，默认跳过。

运行方式（需真实 API Key）::

    RUN_EVALS=1 pytest -m eval -q

用于 prompt / 模型 / 工具变更后的回归评估；启发式评分不消耗判分 token。
"""
import os

import pytest

pytestmark = pytest.mark.eval

_THRESHOLD = 0.7


def test_eval_suite_passes_threshold():
    if os.environ.get("RUN_EVALS") != "1":
        pytest.skip("设置 RUN_EVALS=1 并配置真实 API Key 后运行离线评估")
    from evals.runner import load_cases, run_eval

    try:
        report = run_eval(load_cases())
    except RuntimeError as e:
        pytest.skip(f"缺少 API Key：{e}")

    assert report["passed"], (
        f"评估均分 {report['mean_score']} 低于阈值 {_THRESHOLD}；"
        f"明细: {[(c['id'], c['score'], c['called_tools']) for c in report['cases']]}"
    )
