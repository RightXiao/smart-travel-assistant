"""LLM-as-judge：按 rubric 对 Agent 回复做质量评分。

评分维度（0~1，取平均）：相关性、事实依据（是否与工具结果一致、无编造）、
完整性、可操作性。判分模型走与主 Agent 相同的多厂商 LLM 配置
（``build_chat_model``），温度 0 保证可复现；输出强制 JSON，
解析失败时降级为 0 分并记录原因。
"""
from __future__ import annotations

import json
import re

from src.config.llm import build_chat_model

JUDGE_SYSTEM = """你是旅行助手回答质量的严格评审。给定【用户问题】和【助手回答】，
从四个维度各打 0~1 分（可取 0.5）：
1. relevance 相关性：回答是否针对用户问题；
2. grounding 事实依据：是否基于工具查询结果陈述，没有编造具体景点/价格/营业信息；
3. completeness 完整性：用户关心的要点是否覆盖；
4. actionability 可操作性：建议是否具体可执行。

只输出 JSON，格式：
{"scores": {"relevance": x, "grounding": x, "completeness": x, "actionability": x}, "reasons": ["...", "..."]}"""

JUDGE_USER_TMPL = """【用户问题】
{question}

【助手回答】
{response}"""


def judge_response(question: str, response: str) -> dict:
    """调用判分模型，返回 ``{"score": float, "reasons": [...]}``。"""
    llm = build_chat_model(temperature=0, max_tokens=512)
    result = llm.invoke(
        [
            {"role": "system", "content": JUDGE_SYSTEM},
            {
                "role": "user",
                "content": JUDGE_USER_TMPL.format(question=question, response=response),
            },
        ]
    )
    return _parse_verdict(getattr(result, "content", ""))


def _parse_verdict(content) -> dict:
    """从模型输出中稳健提取 JSON 判分（失败返回 0 分）。"""
    text = (
        content
        if isinstance(content, str)
        else "".join(b.get("text", "") for b in content if isinstance(b, dict))
    )
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"score": 0.0, "reasons": [f"judge 输出无法解析: {text[:200]}"]}
    try:
        data = json.loads(match.group(0))
        scores = data.get("scores", {})
        values = [float(v) for v in scores.values() if isinstance(v, (int, float))]
        if not values:
            raise ValueError("scores 为空")
        reasons = data.get("reasons", [])
        return {"score": round(sum(values) / len(values), 3), "reasons": reasons}
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        return {"score": 0.0, "reasons": [f"judge 结果解析失败: {e}"]}
