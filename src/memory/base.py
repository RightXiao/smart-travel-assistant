from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseMemory(ABC):
    """记忆系统基类。"""
    
    @abstractmethod
    def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """添加消息到记忆。
        
        Args:
            session_id: 会话ID。
            message: 消息内容，格式为 {"role": "user"|"assistant", "content": "..."}。
        """
        pass
    
    @abstractmethod
    def get_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取历史消息。
        
        Args:
            session_id: 会话ID。
            limit: 返回的最大消息数量。
            
        Returns:
            历史消息列表。
        """
        pass
    
    @abstractmethod
    def clear(self, session_id: str) -> None:
        """清除会话记忆。
        
        Args:
            session_id: 会话ID。
        """
        pass
