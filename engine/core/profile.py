"""能力档案管理器 —— 读写 abilities.md，评级计算，学习历史记录

能力档案是智序者的"代码水平画像"，按语言/领域维度展示知识积累量、
自动评级（客观指标）和学习历史。与 TaxonomyManager 配合：
- TaxonomyManager 提供各 parent 的最大可学主题数 → 用于比例评级
- ProfileManager 追踪已学主题和知识条目
"""

from pathlib import Path
from datetime import date
from engine.log import get_logger

logger = get_logger(__name__)


class ProfileManager:
    """能力档案管理器

    维护 memory/profile/abilities.md，记录各编程语言/领域的知识积累情况。
    评级规则（纯客观指标，不依赖 Brain 自评）：
      0 条 = 未接触
      1-3 条 = 入门
      4-7 条 = 进阶
      8+ = 熟练
    """

    def __init__(self, root: Path):
        self.root = root
        self.profile_path = root / "memory" / "profile" / "abilities.md"
        self._ensure_profile()

    def _ensure_profile(self) -> None:
        """确保档案文件和目录存在"""
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.profile_path.exists():
            self._write_template()

    def _write_template(self) -> None:
        """写入初始档案模板"""
        template = (
            "# 智序者能力档案\n\n"
            "> 本文档由 ProfileManager 自动维护，记录编程语言领域的知识积累与水平评级。\n"
            "> 评级规则（客观指标）：0条=未接触 / 1-3条=入门 / 4-7条=进阶 / 8+=熟练\n\n"
            "## 编程语言与领域\n\n"
            "| 语言/领域 | 水平 | 知识条数 | 最近学习 |\n"
            "|-----------|------|----------|----------|\n\n"
            "## 技能清单\n\n"
            "- （随 factory.py 技能注册自动更新）\n\n"
            "## 学习历史\n\n"
            "（每完成一次学习任务后自动追加）\n"
        )
        self.profile_path.write_text(template, encoding="utf-8")

    @staticmethod
    def level(count: int) -> str:
        """根据知识条数计算水平等级"""
        if count == 0:
            return "未接触"
        elif count <= 3:
            return "入门"
        elif count <= 7:
            return "进阶"
        else:
            return "熟练"

    def record_learning(
        self,
        parent: str,
        topic: str,
        summary: str = "",
        source_repo: str = "",
    ) -> dict:
        """记录一次学习任务完成后的档案更新（幂等：重复学习同一主题不重复计数）。

        自动检测该 parent 下已学主题集合，若 topic 已存在则更新（刷新日期和摘要），
        若不存在则计数 +1 并追加新条目。

        Args:
            parent: 所属语言/领域（对应 taxonomy 节点的 parent 字段）
            topic: 学到的主题名
            summary: 学习要点摘要（写入学习历史）
            source_repo: 来源仓库 URL

        Returns:
            dict: {"is_new": bool, "count": int, "level": str}
                is_new=True 表示首次学习该主题（count+1），False 表示复习更新
        """
        content = self.profile_path.read_text(encoding="utf-8")
        today = date.today().isoformat()

        # 检测该主题是否已学过（在学习历史中查找）
        history_header = "## 学习历史\n"
        is_new_topic = True
        if history_header in content:
            history_section = content[content.index(history_header) + len(history_header):]
            # 简单检测：学习历史条目中是否包含该 topic 名
            # 条目格式：- **日期** | topic名
            topic_marker = f"| {topic}"
            if topic_marker in history_section:
                is_new_topic = False

        # 计算当前 count
        data = self.load()
        current_count = data["languages"].get(parent, {}).get("count", 0)
        if is_new_topic:
            total_count = current_count + 1
        else:
            total_count = current_count  # 复习不增加计数

        # 更新 parent 在表格中的行
        parent_escaped = parent.replace("|", "\\|")
        target_line = f"| {parent} |"
        new_row = f"| {parent} | {self.level(total_count)} | {total_count} | {today} |"

        if target_line in content:
            content = content.replace(target_line, new_row, 1)
        else:
            table_end = content.find("\n\n", content.find("|-----------|"))
            if table_end == -1:
                table_end = content.find("## 技能清单")
            if table_end == -1:
                table_end = len(content)
            content = content[:table_end] + f"\n{new_row}" + content[table_end:]

        # 追加/更新学习历史
        if history_header in content:
            entry_lines = [f"- **{today}** | {topic}"]
            if summary:
                entry_lines.append(f"  - {summary[:200]}")
            if source_repo:
                entry_lines.append(f"  - 📦 来源：{source_repo}")
            if is_new_topic:
                insert_pos = content.index(history_header) + len(history_header)
                content = content[:insert_pos] + "\n".join(entry_lines) + "\n" + content[insert_pos:]
            # 复习场景：不重复追加历史，只更新日期（表格行已更新 last_study 日期）

        # 原子写入
        tmp = self.profile_path.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self.profile_path)
        action = "新学" if is_new_topic else "复习"
        logger.info(f"能力档案已更新({action}): {parent} ({topic}) → {self.level(total_count)}({total_count}条)")

        return {"is_new": is_new_topic, "count": total_count, "level": self.level(total_count)}

    def has_topic(self, parent: str, topic: str) -> bool:
        """检查某个主题是否已学习过"""
        data = self.load()
        history = data.get("history", [])
        topic_marker = f"| {topic}"
        return any(topic_marker in h for h in history)

    def load(self) -> dict:
        """读取当前能力档案数据（供 API 返回 JSON）"""
        if not self.profile_path.exists():
            self._ensure_profile()

        content = self.profile_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # 解析语言表格
        languages = {}
        in_table = False
        for line in lines:
            line = line.strip()
            if line.startswith("| 语言/领域"):
                in_table = True
                continue
            if line.startswith("|-----------"):
                continue
            if in_table and line.startswith("| ") and " | " in line:
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 4 and parts[0]:
                    languages[parts[0]] = {
                        "level": parts[1].strip() if len(parts) > 1 else "未接触",
                        "count": int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 0,
                        "last_study": parts[3].strip() if len(parts) > 3 else "-",
                    }
            elif in_table and line == "":
                in_table = False

        # 解析学习历史
        history = []
        in_history = False
        for line in lines:
            if line.strip().startswith("## 学习历史"):
                in_history = True
                continue
            if in_history and line.startswith("## "):
                break
            if in_history and line.strip():
                history.append(line.strip())

        return {
            "languages": languages,
            "history": history[-20:],  # 最近 20 条
        }

    def get_language_stats(self, parent: str) -> dict:
        """获取某个语言/领域的当前统计"""
        data = self.load()
        return data["languages"].get(parent, {
            "level": "未接触",
            "count": 0,
            "last_study": "-",
        })
