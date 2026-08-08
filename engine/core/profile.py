"""能力档案管理器 —— 读写 abilities.md，评级计算，学习历史记录

能力档案是智序者的"代码水平画像"，按语言/领域维度展示知识积累量、
自动评级（客观指标）和学习历史。与 TaxonomyManager 配合：
- TaxonomyManager 提供各 parent 的最大可学主题数 → 用于比例评级
- ProfileManager 追踪已学主题和知识条目
"""

import re
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

    def _get_learned_topics(self) -> set[tuple[str, str]]:
        """从学习历史中提取已学过的 (parent, topic) 集合

        学习历史条目格式：- **日期** | topic名
        注意：历史条目不直接记录 parent，需要通过表格和实际知识文件来推断。
        但我们可以直接通过 knowledge/languages/ 目录下的文件来判断真正已学的主题。
        """
        learned = set()
        knowledge_dir = self.root / "memory" / "knowledge" / "languages"
        if knowledge_dir.exists():
            for parent_dir in knowledge_dir.iterdir():
                if parent_dir.is_dir():
                    for kf in parent_dir.glob("*.md"):
                        learned.add((parent_dir.name, kf.stem))
        return learned

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

        # 用真实知识文件检测是否为新主题（最可靠）
        learned = self._get_learned_topics()
        is_new_topic = (parent, topic) not in learned

        # 统计当前 parent 的已学主题数（从实际文件统计，而非表格count）
        knowledge_dir = self.root / "memory" / "knowledge" / "languages" / parent
        current_count = 0
        if knowledge_dir.exists():
            current_count = len(list(knowledge_dir.glob("*.md")))

        if is_new_topic:
            total_count = current_count + 1
        else:
            total_count = current_count

        new_row = f"| {parent} | {self.level(total_count)} | {total_count} | {today} |"

        # 整行替换：用正则找到以 | parent | 开头的表格行，替换整行
        # 表格行格式：| parent | level | count | date |（可能有损坏的多余列）
        line_pattern = re.compile(
            r'^\| ' + re.escape(parent) + r' \|[^\n]*$',
            re.MULTILINE
        )
        if line_pattern.search(content):
            content = line_pattern.sub(new_row, content, count=1)
        else:
            # 在表格分隔行后插入新行
            sep_match = re.search(r'^\|[-\s|]+\|$', content, re.MULTILINE)
            if sep_match:
                insert_pos = sep_match.end()
                content = content[:insert_pos] + "\n" + new_row + content[insert_pos:]
            else:
                # 找不到分隔行，在技能清单前插入
                skills_pos = content.find("## 技能清单")
                if skills_pos != -1:
                    content = content[:skills_pos] + new_row + "\n\n" + content[skills_pos:]
                else:
                    content += "\n" + new_row + "\n"

        # 清理可能因历史bug导致的损坏行（删除多余的表格行）
        content = self._cleanup_corrupted_rows(content, parent, new_row)

        # 追加/更新学习历史
        history_header = "## 学习历史\n"
        if history_header in content:
            # 截断 summary：取第一行有意义的文字，最多 100 字
            brief = ""
            if summary:
                # 去除 markdown 标记，取第一段非空文字
                clean = re.sub(r'[#*`>\-\n]', ' ', summary).strip()
                clean = re.sub(r'\s+', ' ', clean)
                brief = clean[:100] if clean else ""

            entry_lines = [f"- **{today}** | {topic}"]
            if brief:
                entry_lines.append(f"  - {brief}")
            if source_repo:
                entry_lines.append(f"  - 📦 来源：{source_repo}")
            if is_new_topic:
                insert_pos = content.index(history_header) + len(history_header)
                # 跳过模板提示文字
                template_hint = "（每完成一次学习任务后自动追加）"
                rest = content[insert_pos:]
                if rest.startswith(template_hint):
                    insert_pos += len(template_hint)
                content = content[:insert_pos] + "\n".join(entry_lines) + "\n" + content[insert_pos:]

        # 原子写入
        tmp = self.profile_path.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self.profile_path)
        action = "新学" if is_new_topic else "复习"
        logger.info(f"能力档案已更新({action}): {parent} ({topic}) → {self.level(total_count)}({total_count}条)")

        return {"is_new": is_new_topic, "count": total_count, "level": self.level(total_count)}

    def _cleanup_corrupted_rows(self, content: str, parent: str, new_row: str) -> str:
        """清理因历史bug导致的重复/损坏表格行"""
        lines = content.split("\n")
        seen_parent = False
        result = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"| {parent} |") and stripped.endswith("|"):
                if not seen_parent:
                    result.append(new_row)
                    seen_parent = True
                # 跳过后续重复的 parent 行
                continue
            result.append(line)
        return "\n".join(result)

    def get_learned_topics(self, parent: str) -> set[str]:
        """获取指定领域下已学过的主题名集合"""
        knowledge_dir = self.root / "memory" / "knowledge" / "languages" / parent
        topics = set()
        if knowledge_dir.exists():
            for kf in knowledge_dir.glob("*.md"):
                topics.add(kf.stem)
        return topics

    def has_topic(self, parent: str, topic: str) -> bool:
        """检查某个主题是否已学习过"""
        knowledge_path = self.root / "memory" / "knowledge" / "languages" / parent / f"{topic}.md"
        return knowledge_path.exists()

    def load(self) -> dict:
        """读取当前能力档案数据（供 API 返回 JSON）

        同时根据实际知识文件修复表格中的计数，避免因历史bug导致数据不准。
        """
        if not self.profile_path.exists():
            self._ensure_profile()

        content = self.profile_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # 解析语言表格
        languages = {}
        in_table = False
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("| 语言/领域"):
                in_table = True
                continue
            if line_stripped.startswith("|-----------"):
                continue
            if in_table and line_stripped.startswith("| ") and " | " in line_stripped:
                parts = [p.strip() for p in line_stripped.strip("|").split("|")]
                if len(parts) >= 4 and parts[0]:
                    lang_name = parts[0].strip()
                    # count 以实际知识文件数为准，而非表格中的数字（表格可能因bug不准确）
                    knowledge_dir = self.root / "memory" / "knowledge" / "languages" / lang_name
                    actual_count = 0
                    if knowledge_dir.exists():
                        actual_count = len(list(knowledge_dir.glob("*.md")))
                    if actual_count > 0:
                        last_study = parts[3].strip() if len(parts) > 3 else "-"
                        languages[lang_name] = {
                            "level": self.level(actual_count),
                            "count": actual_count,
                            "last_study": last_study,
                        }
            elif in_table and line_stripped == "":
                in_table = False

        # 如果表格中有但实际文件数=0的语言，也要清理（此处不写回，只影响返回数据）

        # 解析学习历史
        history = []
        in_history = False
        for line in lines:
            if line.strip().startswith("## 学习历史"):
                in_history = True
                continue
            if in_history and line.startswith("## "):
                break
            if in_history and line.strip() and not line.strip().startswith("（"):
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
