"""工具输出防护栏测试。"""
from src.utils.sanitize import redact_secrets, sanitize_tool_output


class TestRedactSecrets:
    def test_redacts_sk_prefix_keys(self):
        text = "认证失败 key=sk-abc123DEF_-456ghi 请检查"
        assert "sk-abc123DEF" not in redact_secrets(text)
        assert "[REDACTED]" in redact_secrets(text)

    def test_redacts_32hex_amap_keys(self):
        key = "0123456789abcdef0123456789abcdef"
        assert key not in redact_secrets(f"key={key}&status=0")

    def test_keeps_normal_text(self):
        text = "故宫博物院位于北京市东城区，门票60元"
        assert redact_secrets(text) == text

    def test_short_hex_not_redacted(self):
        """非 32 位的短十六进制串（如坐标、颜色码）不应误伤。"""
        text = "坐标 116.39,39.90 色值 #ff0044 距离 39.90"
        assert redact_secrets(text) == text


class TestSanitizeToolOutput:
    def test_removes_control_chars(self):
        assert sanitize_tool_output("a\x00b\x08c") == "abc"

    def test_preserves_newline_and_tab(self):
        assert sanitize_tool_output("a\nb\tc") == "a\nb\tc"

    def test_removes_zero_width_chars(self):
        """零宽字符（隐写注入载体）应被清除。"""
        text = "正\u200b常\u200c文\u2060本\ufeff"
        assert sanitize_tool_output(text) == "正常文本"

    def test_truncates_long_output(self):
        text = "长" * 5000
        result = sanitize_tool_output(text, max_chars=100)
        assert result.startswith("长" * 100)
        assert "截断" in result

    def test_non_string_input_coerced(self):
        assert sanitize_tool_output(123) == "123"

    def test_full_pipeline(self):
        dirty = "故宫\u200b 门票60元\x07 key=sk-secret123456"
        clean = sanitize_tool_output(dirty)
        assert "\u200b" not in clean
        assert "\x07" not in clean
        assert "sk-secret123456" not in clean
