"""工具调用记录器：包装工具列表，记录 Agent 实际调用的工具与参数。"""
from langchain_core.tools import StructuredTool


def wrap_tools_with_recorder(tools: list) -> tuple:
    """包装每个工具：调用时把 ``(工具名, 参数)`` 追加进记录列表。

    Returns:
        ``(wrapped_tools, calls)`` —— ``calls`` 是外部持有的记录列表，
        Agent 每次调用工具后会追加 ``{"tool": name, "args": kwargs}``。
    """
    calls: list = []
    wrapped = []
    for tool in tools:
        wrapped.append(
            StructuredTool.from_function(
                func=_make_recorder(tool.name, tool.func, calls),
                name=tool.name,
                description=tool.description,
                args_schema=tool.args_schema,
            )
        )
    return wrapped, calls


def _make_recorder(name: str, func, calls: list):
    def record(**kwargs):
        calls.append({"tool": name, "args": kwargs})
        return func(**kwargs)

    return record
