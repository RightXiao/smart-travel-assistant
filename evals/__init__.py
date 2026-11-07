"""离线评估框架：黄金用例集 + 工具选择评分 + LLM-as-judge。

用法::

    # 启发式评估（需要真实 API Key，验证工具选择与关键内容覆盖）
    python -m evals.runner

    # 启用 LLM-as-judge 质量评分
    python -m evals.runner --judge

    # 输出 JSON 报告（供 CI 消费），低于阈值退出码 1
    python -m evals.runner --json --threshold 0.7

评估维度：
- **工具选择**：用例标注的必备工具是否都被调用（对 Agent 决策的核心度量）；
- **内容覆盖**：回复中是否包含关键信息（城市名等锚点）；
- **质量评分（可选）**：LLM-as-judge 按 rubric 打分（相关性/准确性/完整性）。
"""
