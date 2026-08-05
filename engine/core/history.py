"""对话历史持久化 —— 重启后恢复上下文

将对话历史以 JSONL 格式存入 memory/conversations/，
每次启动自动恢复最近一次会话，reset 时开新会话。
"""

import json
from datetime import datetime
from pathlib import Path

from engine.brain.base import Message


def _deserialize(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=d.get("tool_calls"),
        tool_call_id=d.get("tool_call_id"),
    )


class HistoryStore:
    """对话历史持久化存储。

    每次保存覆盖当前会话文件（完整写入），
    加载时读取全部行还原 Message 列表。
    """

    def __init__(self, root: Path):
        self.dir = root / "memory" / "conversations"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._current: Path | None = None

    def new_session(self) -> Path:
        """开新会话文件，返回文件路径"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._current = self.dir / f"{ts}.jsonl"
        # 创建空文件以在磁盘上声明此会话
        self._current.touch()
        return self._current

    def latest_session(self) -> Path | None:
        """获取最近一次会话文件路径，没有则返回 None"""
        files = sorted(self.dir.glob("*.jsonl"))
        return files[-1] if files else None

    def save(self, messages: list[Message]) -> None:
        """保存当前完整历史到会话文件"""
        if self._current is None:
            self.new_session()
        with open(self._current, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")

    def load(self, filepath: Path) -> list[Message]:
        """从 JSONL 文件加载消息列表，跳过损坏行"""
        messages: list[Message] = []
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(_deserialize(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[HistoryStore] 跳过损坏行 {filepath.name}:{i + 1} — {e}")
        return messages
