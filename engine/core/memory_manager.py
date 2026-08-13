"""记忆管理器 —— 协调检索 + 构建上下文

MemoryManager 是连接"记忆读取"与"Agent 上下文"的桥梁。
每轮对话前，Agent 调用 build_context() 检索相关历史经验，
将结果格式化为一段简洁文本，注入 system prompt。
"""

import json
from datetime import datetime

from engine.core.memory_reader import MemoryReader
from engine.config import config

# 单条目展示最大字符数（防止上下文膨胀）
MAX_ENTRY_CHARS = config.memory.entry_max_chars
# 提示前缀
CONTEXT_PREFIX = "【相关历史经验】"

# 记忆复用事件落盘文件名（成长可视化数据源，位于 .runtime/ 已被 gitignore 隔离）
REUSE_FILE_NAME = "growth_reuse.jsonl"


def _record_reuse(root, query: str, entries: list[dict]) -> None:
    """把一次记忆命中落盘为复用事件（供 Web 成长时间线展示"越用越懂你"）。

    落盘失败静默吞掉，绝不阻断主流程。
    """
    try:
        runtime_dir = root / ".runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "query": query[:200],
            "hits": [
                {
                    "source": e.get("source", ""),
                    "date": e.get("date", ""),
                    "score": e.get("score", 0),
                    "preview": (e.get("content", "") or "")[:120],
                }
                for e in entries
            ],
        }
        with open(runtime_dir / REUSE_FILE_NAME, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


class MemoryManager:
    """记忆管理器 —— 检索 + 格式化 + 上下文注入"""

    def __init__(self, reader: MemoryReader):
        self.reader = reader

    def build_context(self, user_input: str, max_entries: int | None = None) -> str:
        """根据用户输入检索相关记忆，返回格式化的上下文字符串

        返回空字符串表示无相关记忆。
        结果适合直接拼接到 system prompt 末尾。
        """
        if max_entries is None:
            max_entries = config.memory.max_entries
        entries = self.reader.retrieve(user_input, max_entries)
        if not entries:
            return ""

        _record_reuse(self.reader.root, user_input, entries)

        lines = [CONTEXT_PREFIX]
        for i, e in enumerate(entries):
            content = e["content"][:MAX_ENTRY_CHARS]
            if len(e["content"]) > MAX_ENTRY_CHARS:
                content += "…"
            source_label = {"diary": "日记", "experience": "经验", "knowledge": "知识"}.get(
                e["source"], e["source"],
            )
            lines.append(f"\n[{i + 1}] {e['date']} ({source_label}, 相关度 {e['score']})\n{content}")

        return "\n".join(lines)
