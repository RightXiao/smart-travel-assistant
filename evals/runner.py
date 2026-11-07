"""评估运行器：执行黄金用例集并产出评分报告。

用法::

    python -m evals.runner                 # 启发式评分（需真实 API Key）
    python -m evals.runner --judge         # 叠加 LLM-as-judge 质量评分
    python -m evals.runner --json --threshold 0.7
"""
from __future__ import annotations

import argparse
import json
import sys

from evals.cases import load_cases
from evals.judge import judge_response
from evals.recording import wrap_tools_with_recorder
from src.agents.travel_assistant import TravelAssistant
from src.config.settings import require_api_keys

# 评分权重：工具选择是 Agent 决策的核心指标
TOOL_WEIGHT = 0.6
MUST_WEIGHT = 0.4


def _tool_score(expected: list, called: list) -> float:
    """必备工具覆盖率；空 expected 表示不应调用工具。"""
    if not expected:
        return 1.0 if not called else 0.0
    called_names = {c["tool"] for c in called}
    covered = sum(1 for t in set(expected) if t in called_names)
    return covered / len(set(expected))


def _must_score(must_include: list, response: str) -> float:
    if not must_include:
        return 1.0
    hit = sum(1 for anchor in must_include if anchor in response)
    return hit / len(must_include)


def run_eval(
    cases: list,
    assistant: TravelAssistant = None,
    use_judge: bool = False,
    threshold: float = 0.7,
) -> dict:
    """跑完整评估，返回报告 dict（含 mean_score 与逐用例明细）。

    未显式提供 assistant 时使用临时目录记忆后端，评估对话不污染运行时 ``memory/``。
    """
    if assistant is None:
        import tempfile

        from src.memory.file_memory import FileMemory

        tmpdir = tempfile.mkdtemp(prefix="travel-eval-")
        assistant = TravelAssistant(memory=FileMemory(storage_dir=tmpdir))

    results = []
    for case in cases:
        wrapped_tools, calls = wrap_tools_with_recorder(assistant.tools)
        # 以记录器替换工具并重建 agent（仅影响本次评估实例）
        assistant.tools = wrapped_tools
        assistant.agent = assistant._create_agent()

        response = assistant.chat(case["input"], session_id=f"eval-{case['id']}")
        tool_score = _tool_score(case.get("expected_tools", []), calls)
        must_score = _must_score(case.get("must_include", []), response)

        if case.get("expected_tools") and case.get("must_include"):
            heuristic = TOOL_WEIGHT * tool_score + MUST_WEIGHT * must_score
        elif case.get("expected_tools"):
            heuristic = tool_score
        else:
            heuristic = must_score

        entry = {
            "id": case["id"],
            "capability": case.get("capability", ""),
            "called_tools": [c["tool"] for c in calls],
            "tool_score": round(tool_score, 3),
            "must_score": round(must_score, 3),
            "heuristic_score": round(heuristic, 3),
        }

        if use_judge:
            verdict = judge_response(case["input"], response)
            # 启发式与 judge 各占一半，避免单一维度失真
            entry["judge_score"] = verdict["score"]
            entry["judge_reasons"] = verdict.get("reasons", [])
            entry["score"] = round(0.5 * heuristic + 0.5 * verdict["score"], 3)
        else:
            entry["score"] = round(heuristic, 3)

        results.append(entry)

    mean_score = (
        round(sum(r["score"] for r in results) / len(results), 3) if results else 0.0
    )
    return {
        "mean_score": mean_score,
        "threshold": threshold,
        "passed": mean_score >= threshold,
        "case_count": len(results),
        "cases": results,
    }


def print_report(report: dict) -> None:
    print(
        f"\n📊 评估结果：mean={report['mean_score']} "
        f"阈值={report['threshold']} 通过={report['passed']} "
        f"({report['case_count']} 用例)\n"
    )
    print(f"{'用例':<24}{'能力':<12}{'工具':<8}{'内容':<8}{'总分':<8} 工具调用")
    print("-" * 88)
    for c in report["cases"]:
        tools = ",".join(c["called_tools"])[:34] or "(未调用)"
        print(
            f"{c['id']:<24}{c['capability']:<12}"
            f"{c['tool_score']:<8}{c['must_score']:<8}{c['score']:<8} {tools}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="旅行助手离线评估")
    parser.add_argument("--cases", default=None, help="用例集 JSON 路径（默认内置）")
    parser.add_argument("--judge", action="store_true", help="启用 LLM-as-judge 质量评分")
    parser.add_argument("--threshold", type=float, default=0.7, help="通过阈值")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出报告")
    args = parser.parse_args()

    try:
        require_api_keys()
        report = run_eval(
            load_cases(args.cases), use_judge=args.judge, threshold=args.threshold
        )
    except RuntimeError as e:
        print(f"评估需要真实 API Key：{e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
