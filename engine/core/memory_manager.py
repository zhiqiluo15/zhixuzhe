"""记忆管理器 —— 协调检索 + 构建上下文

MemoryManager 是连接"记忆读取"与"Agent 上下文"的桥梁。
每轮对话前，Agent 调用 build_context() 检索相关历史经验，
将结果格式化为一段简洁文本，注入 system prompt。
"""

from engine.core.memory_reader import MemoryReader

# 单条目展示最大字符数（防止上下文膨胀）
MAX_ENTRY_CHARS = 300
# 提示前缀
CONTEXT_PREFIX = "【相关历史经验】"


class MemoryManager:
    """记忆管理器 —— 检索 + 格式化 + 上下文注入"""

    def __init__(self, reader: MemoryReader):
        self.reader = reader

    def build_context(self, user_input: str, max_entries: int = 3) -> str:
        """根据用户输入检索相关记忆，返回格式化的上下文字符串

        返回空字符串表示无相关记忆。
        结果适合直接拼接到 system prompt 末尾。
        """
        entries = self.reader.retrieve(user_input, max_entries)
        if not entries:
            return ""

        lines = [CONTEXT_PREFIX]
        for i, e in enumerate(entries):
            content = e["content"][:MAX_ENTRY_CHARS]
            if len(e["content"]) > MAX_ENTRY_CHARS:
                content += "…"
            source_label = "日记" if e["source"] == "diary" else "经验"
            lines.append(f"\n[{i + 1}] {e['date']} ({source_label}, 相关度 {e['score']})\n{content}")

        return "\n".join(lines)
