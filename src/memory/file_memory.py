import json
from pathlib import Path
from typing import List, Dict, Any
from src.memory.base import BaseMemory
from src.utils.logger import logger


class FileMemory(BaseMemory):
    """基于文件的记忆系统。"""
    
    def __init__(self, storage_dir: str = "memory"):
        """初始化文件记忆系统。
        
        Args:
            storage_dir: 存储目录路径。
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
    
    def _get_file_path(self, session_id: str) -> Path:
        """获取会话文件路径。
        
        Args:
            session_id: 会话ID。
            
        Returns:
            会话文件路径。
        """
        # 清理 session_id，移除不安全的字符
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.storage_dir / f"{safe_id}.json"
    
    def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """添加消息到文件记忆。
        
        Args:
            session_id: 会话ID。
            message: 消息内容。
        """
        file_path = self._get_file_path(session_id)
        messages = self.get_messages(session_id)
        messages.append(message)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
    
    def get_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取历史消息。
        
        Args:
            session_id: 会话ID。
            limit: 返回的最大消息数量。
            
        Returns:
            历史消息列表。
        """
        file_path = self._get_file_path(session_id)
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                messages = json.load(f)
            return messages[-limit:]
        except Exception as e:
            logger.error(f"读取消息失败: {e}")
            return []
    
    def clear(self, session_id: str) -> None:
        """清除会话记忆。
        
        Args:
            session_id: 会话ID。
        """
        file_path = self._get_file_path(session_id)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.error(f"清除记忆失败: {e}")
