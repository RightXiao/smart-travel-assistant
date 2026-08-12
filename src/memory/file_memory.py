import hashlib
import json
import os
import threading
from pathlib import Path
from typing import List, Dict, Any

from src.memory.base import BaseMemory
from src.utils.logger import logger


class FileMemory(BaseMemory):
    """基于文件的记忆系统。

    每个会话（``session_id``）对应 ``<storage_dir>/<safe_id>.json`` 一个 JSON 文件。
    文件名使用 ``session_id`` 的 SHA-256 摘要，既防止目录穿越，也避免不同原始 id
    （如 ``a/b`` 与 ``a.b``）清洗后碰撞。文件内容为 ``{"session_id": ..., "messages": [...]}``，
    以便 ``list_sessions()`` 能还原原始会话 id。

    写入采用「临时文件 + ``os.replace`` 原子替换」并加进程内锁，避免并发请求下
    历史丢失或写坏 JSON。
    """

    def __init__(self, storage_dir: str = "memory"):
        """初始化文件记忆系统。

        Args:
            storage_dir: 存储目录路径（相对路径基于工作目录）。
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()

    def _get_file_path(self, session_id: str) -> Path:
        """获取会话文件路径。

        用 SHA-256 摘要作为文件名：任意 session_id 都映射为固定长度十六进制串，
        天然规避路径穿越与非法字符，且不同原始 id 不会碰撞（除哈希碰撞）。
        """
        if not session_id:
            safe_id = "default"
        else:
            safe_id = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
        return self.storage_dir / f"{safe_id}.json"

    def _atomic_dump(self, file_path: Path, session_id: str, messages: List[Dict[str, Any]]) -> None:
        """先写临时文件再原子替换，避免写一半崩溃留下损坏 JSON。"""
        tmp_path = file_path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"session_id": session_id, "messages": messages},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp_path, file_path)
        except OSError as e:
            logger.error("保存消息失败: %s", e)
            # 清理可能残留的临时文件
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def add_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """添加消息到文件记忆。"""
        file_path = self._get_file_path(session_id)
        with self._lock:
            messages = self.get_messages(session_id, limit=10_000)
            messages.append(message)
            self._atomic_dump(file_path, session_id, messages)

    def add_messages(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        """批量追加消息（原子写一次，比逐条 add_message 高效）。"""
        if not messages:
            return
        file_path = self._get_file_path(session_id)
        with self._lock:
            existing = self.get_messages(session_id, limit=10_000)
            existing.extend(messages)
            self._atomic_dump(file_path, session_id, existing)

    def get_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取历史消息（返回最近 ``limit`` 条）。"""
        file_path = self._get_file_path(session_id)
        if not file_path.exists():
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("读取消息失败: %s", e)
            return []

        # 兼容两种文件格式：{"session_id": ..., "messages": [...]} 或旧版裸 list
        if isinstance(data, dict):
            messages = data.get("messages", [])
        else:
            messages = data
        if not isinstance(messages, list):
            return []

        if limit > 0:
            return messages[-limit:]
        return messages

    def clear(self, session_id: str) -> None:
        """清除会话记忆。"""
        file_path = self._get_file_path(session_id)
        with self._lock:
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError as e:
                    logger.error("清除记忆失败: %s", e)

    def list_sessions(self) -> List[str]:
        """列出所有已存在的会话 id（排序返回，保证稳定）。"""
        sessions: List[str] = []
        for p in self.storage_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("session_id"):
                sessions.append(data["session_id"])
            else:
                # 旧版裸 list 文件无法还原原始 id，回退到文件名
                sessions.append(p.stem)
        return sorted(sessions)
