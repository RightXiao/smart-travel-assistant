from src.utils.logger import setup_logger


class TestLogger:
    """日志工具测试（覆盖 P1：重复 import 不重复添加 handler）。"""

    def test_no_duplicate_handlers(self):
        logger = setup_logger("travel_agent")
        before = len(logger.handlers)
        logger2 = setup_logger("travel_agent")  # 再次调用
        assert logger2 is logger
        assert len(logger2.handlers) == before  # 不应增加

    def test_independent_loggers(self):
        a = setup_logger("travel_agent_a")
        b = setup_logger("travel_agent_b")
        assert len(a.handlers) >= 1
        assert len(b.handlers) >= 1

    def test_propagate_disabled(self):
        logger = setup_logger("travel_agent")
        assert logger.propagate is False
