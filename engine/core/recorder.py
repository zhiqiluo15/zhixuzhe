"""记忆记录器 —— 将每次交互写入灵魂层（memory/）"""

from datetime import datetime
from pathlib import Path

from engine.log import get_logger

logger = get_logger(__name__)


class Recorder:
    """将 Agent 交互记录到 memory/diary/（私有灵魂层）"""

    def __init__(self, root: Path):
        self.root = root
        self.diary_dir = root / "memory" / "diary"
        self.diary_dir.mkdir(parents=True, exist_ok=True)
        self.experience_dir = root / "memory" / "experience"
        self.experience_dir.mkdir(parents=True, exist_ok=True)

    def record(self, user_input: str, response: str) -> None:
        """记录一次交互"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"## {timestamp}\n\n**问**：{user_input}\n\n**答**：{response}\n\n---\n\n"
        self._write(entry)

    def record_task(
        self,
        goal: str,
        plan: list[str],
        step_results: list[str],
        final_answer: str,
        plan_source: str = "llm",
    ) -> None:
        """记录一次自主任务执行"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"## [任务] {timestamp}\n\n"
        entry += f"**目标**：{goal}\n\n"
        entry += f"**规划来源**：{plan_source}\n"
        entry += f"**计划**（{len(plan)} 步）：\n"
        for i, s in enumerate(plan):
            status = "✅" if i < len(step_results) else "⏳"
            entry += f"{i + 1}. {s} {status}\n"
        entry += "\n**执行结果**：\n"
        for i, r in enumerate(step_results):
            entry += f"- 步骤 {i + 1}: {r[:200]}{'...' if len(r) > 200 else ''}\n"
        entry += f"\n**最终结论**：\n{final_answer}\n\n---\n\n"
        self._write(entry)

    def record_experience(self, scene: str, lesson: str) -> None:
        """记录一条个人经验到 memory/experience/

        Args:
            scene: 场景描述（发生了什么）
            lesson: 吸取的教训/经验
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"## {timestamp}\n\n**场景**：{scene}\n\n**教训**：{lesson}\n\n---\n\n"
        self._write_experience(entry)

    def _write_experience(self, entry: str) -> None:
        """写经验到当日经验文件，自动去重。

        去重策略：提取 entry 中的「场景」和「教训」行，
        与当日已有经验逐条对比，完全相同则跳过写入。
        """
        filepath = self.experience_dir / f"{datetime.now().strftime('%Y%m%d')}.md"

        # 提取本次的场景和教训用于去重比较
        scene_line = ""
        lesson_line = ""
        for line in entry.splitlines():
            if line.startswith("**场景**"):
                scene_line = line.strip()
            elif line.startswith("**教训**"):
                lesson_line = line.strip()

        # 检查当日文件中是否已有相同条目
        if filepath.exists() and scene_line and lesson_line:
            existing = filepath.read_text(encoding="utf-8")
            if scene_line in existing and lesson_line in existing:
                logger.debug(f"经验已存在，跳过写入: {scene_line[:50]}...")
                return

        if not filepath.exists():
            date_str = datetime.now().strftime("%Y-%m-%d")
            entry = f"# 智序者经验 - {date_str}\n\n" + entry
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)

    def _write(self, entry: str) -> None:
        """写条目到当日日记文件，首次写入时自动加 header"""
        filepath = self._today_file()
        if not filepath.exists():
            date_str = datetime.now().strftime("%Y-%m-%d")
            entry = f"# 智序者日记 - {date_str}\n\n" + entry
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)

    def _today_file(self) -> Path:
        return self.diary_dir / f"{datetime.now().strftime('%Y%m%d')}.md"
