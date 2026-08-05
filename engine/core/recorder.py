"""记忆记录器 —— 将每次交互写入灵魂层（memory/）"""

from datetime import datetime
from pathlib import Path


class Recorder:
    """将 Agent 交互记录到 memory/diary/（私有灵魂层）"""

    def __init__(self, root: Path):
        self.root = root
        self.diary_dir = root / "memory" / "diary"
        self.diary_dir.mkdir(parents=True, exist_ok=True)

    def record(self, user_input: str, response: str) -> None:
        """记录一次交互"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"## {timestamp}\n\n**问**：{user_input}\n\n**答**：{response}\n\n---\n\n"

        filepath = self._today_file()
        if not filepath.exists():
            date_str = datetime.now().strftime("%Y-%m-%d")
            header = f"# 智序者日记 - {date_str}\n\n"
            entry = header + entry

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)

    def _today_file(self) -> Path:
        return self.diary_dir / f"{datetime.now().strftime('%Y%m%d')}.md"

    def record_task(
        self,
        goal: str,
        plan: list[str],
        step_results: list[str],
        final_answer: str,
    ) -> None:
        """记录一次自主任务执行"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"## [任务] {timestamp}\n\n"
        entry += f"**目标**：{goal}\n\n"
        entry += f"**计划**（{len(plan)} 步）：\n"
        for i, s in enumerate(plan):
            status = "✅" if i < len(step_results) else "⏳"
            entry += f"{i + 1}. {s} {status}\n"
        entry += "\n**执行结果**：\n"
        for i, r in enumerate(step_results):
            entry += f"- 步骤 {i + 1}: {r[:200]}{'...' if len(r) > 200 else ''}\n"
        entry += f"\n**最终结论**：\n{final_answer}\n\n---\n\n"

        filepath = self._today_file()
        if not filepath.exists():
            date_str = datetime.now().strftime("%Y-%m-%d")
            header = f"# 智序者日记 - {date_str}\n\n"
            entry = header + entry

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)
