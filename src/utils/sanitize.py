"""工具输出防护栏：进入 LLM 上下文前统一清洗。

目标：
- **降低提示注入面**：工具返回的 POI 名 / 地址 / 路线文案是外部数据，
  清除控制字符与零宽字符（常见隐写注入载体）；
- **防密钥泄漏**：脱敏常见密钥形态（``sk-`` 前缀、高德 32 位十六进制 key），
  即使上游异常把 key 带进错误文本也不会进入对话与日志；
- **限制长度**：异常超长的工具输出截断，防止撑爆上下文。

清洗是保守的：只做无副作用的字符级处理，不改动正常业务文案。
"""
from __future__ import annotations

import re

# 常见密钥形态：OpenAI 系 ``sk-`` 前缀；高德 key 为 32 位十六进制
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\b[0-9a-fA-F]{32}\b"),
]

# C0 控制字符（保留 \n \t）与零宽字符
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")

DEFAULT_MAX_CHARS = 4000


def redact_secrets(text: str) -> str:
    """把疑似密钥的子串替换为 ``[REDACTED]``。"""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def sanitize_tool_output(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """清洗工具输出：去控制/零宽字符 → 密钥脱敏 → 限长截断。"""
    if not isinstance(text, str):
        text = str(text)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = redact_secrets(text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（输出过长已截断）"
    return text
