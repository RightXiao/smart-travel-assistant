"""黄金用例集：按能力维度标注必备工具与内容锚点。

字段说明：
- ``id`` / ``capability``：用例标识与能力维度；
- ``input``：用户输入；
- ``expected_tools``：必备工具（评分 = 覆盖比例；空列表表示不应调用任何工具）；
- ``must_include``：回复中必须出现的内容锚点（可为空）。
"""
import json
from pathlib import Path

_CASES_FILE = Path(__file__).parent / "cases.json"


def load_cases(path=None) -> list:
    """加载黄金用例（默认内置用例集）。"""
    file = Path(path) if path else _CASES_FILE
    with open(file, encoding="utf-8") as f:
        cases = json.load(f)
    for case in cases:
        assert case.get("id"), "用例缺少 id"
        assert "input" in case, f"用例 {case['id']} 缺少 input"
        assert isinstance(case.get("expected_tools", []), list)
        assert isinstance(case.get("must_include", []), list)
    return cases
