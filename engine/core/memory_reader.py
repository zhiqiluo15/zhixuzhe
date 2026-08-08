"""记忆读取器 —— 从灵魂层检索相关历史经验

对比 Recorder（只写），MemoryReader 是"只读"端。
闭合了 CHANGELOG 标记的"记忆只写不读"缺陷。

检索策略（v1，无外部依赖）：
- 混合中英文分词（中文 2-gram + 英文单词）
- 关键词重叠评分
- 内容去重（跳过高度相似的条目）
- 按相关度降序返回 top-k
"""

import re
from datetime import datetime
from pathlib import Path

from engine.config import config


# ── 停用词 ──

# 常见中英文停用词（2-gram），这些词在几乎所有文本中出现，无区分度
_STOP_WORDS: set[str] = {
    # 中文高频 bigram
    "什么", "怎么", "这个", "那个", "我们", "他们", "你们", "可以",
    "没有", "知道", "因为", "所以", "但是", "如果", "已经", "还是",
    "不是", "就是", "一个", "都是", "不是", "自己",
    # 英文高频词
    "the", "is", "are", "was", "were", "and", "for", "not",
    "that", "this", "with", "have", "has", "from", "they",
    "will", "would", "could", "should", "been", "being",
}


# ── 分词 ──

def _tokenize(text: str) -> set[str]:
    """混合中英文分词：中文用 2-gram，英文用单词（≥2字符），过滤停用词"""
    tokens: set[str] = set()
    # 英文单词
    for m in re.finditer(r"[a-zA-Z]{2,}", text):
        word = m.group().lower()
        if word not in _STOP_WORDS and len(word) > 1:
            tokens.add(word)
    # 中文 2-gram
    cn = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for i in range(len(cn) - 1):
        bigram = cn[i : i + 2]
        if bigram not in _STOP_WORDS:
            tokens.add(bigram)
    return tokens


# ── 去重 ──

def _jaccard_similarity(a: str, b: str) -> float:
    """计算两段文本的 bigram Jaccard 相似度"""
    if not a or not b:
        return 0.0
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    intersect = ta & tb
    union = ta | tb
    return len(intersect) / len(union)


# ── 条目解析 ──

def _parse_diary_entries(content: str) -> list[dict]:
    """将 Markdown 文件按 ## 分段解析为 {title, body} 列表。

    通用解析器，兼容三种文件格式：
    - 日记：## HH:MM:SS 或 ## [任务] HH:MM:SS
    - 经验：## HH:MM:SS
    - 知识：## 标题文字（无时间戳），### 子标题保留在 body 中

    第一个 ## 之前为文件头（叙述/元数据），跳过。
    """
    entries: list[dict] = []
    lines = content.split("\n")
    current_title = ""
    current_body: list[str] = []
    in_header = True  # 第一个 ## 之前为文件头

    for line in lines:
        # ## 开头（但不是 ### 子标题）= 新条目开始
        if line.startswith("## ") and not line.startswith("### "):
            if current_body:
                entries.append({
                    "title": current_title,
                    "body": "\n".join(current_body).strip(),
                })
            in_header = False
            current_title = line[3:].strip()
            current_body = []
        elif not in_header:
            current_body.append(line)

    # 最后一条
    if current_body:
        entries.append({
            "title": current_title,
            "body": "\n".join(current_body).strip(),
        })

    return entries


def _is_timestamped(line: str) -> bool:
    """判断 ## 行是否以时间戳开头（## HH:MM 或 ## [任务] HH:MM）。

    保留此函数供外部判断条目类型用（日记/经验条目有时间戳，知识条目无）。
    """
    bare = line[3:].strip() if line.startswith("## ") else line.strip()
    # ## HH:MM:SS
    if re.match(r"\d{2}:\d{2}:\d{2}", bare):
        return True
    # ## [任务] HH:MM:SS
    if re.match(r"\[任务\]\s*\d{2}:\d{2}:\d{2}", bare):
        return True
    return False


def _parse_experience_entries(content: str) -> list[dict]:
    """解析经验文件中的条目（## 开头）"""
    return _parse_diary_entries(content)


# ── 评分与检索 ──

def _score(query_terms: set[str], entry: dict) -> float:
    """计算条目对查询的相关度分数（0~1）

    使用 √n 归一化缓解长查询惩罚——查询越长，命中越难，单关键词命中仍有意义。
    例：QLoRA 在 8 词查询中命中 1 次 → 1/√8 ≈ 0.35
    """
    if not query_terms:
        return 0.0
    text = entry["title"] + " " + entry["body"]
    entry_terms = _tokenize(text)
    overlap = query_terms & entry_terms
    if not overlap:
        return 0.0
    return len(overlap) / (len(query_terms) ** 0.5)


class MemoryReader:
    """记忆读取器 —— 从 memory/diary/ 和 memory/experience/ 检索相关条目"""

    def __init__(self, root: Path):
        self.root = root
        self.diary_dir = root / "memory" / "diary"
        self.experience_dir = root / "memory" / "experience"
        self.knowledge_dir = root / "memory" / "knowledge" / "languages"
        self.MIN_SCORE = config.memory.min_score
        self.DEDUP_THRESHOLD = config.memory.dedup_threshold

    # ── 公开接口 ──

    def retrieve(self, query: str, max_entries: int = 5) -> list[dict]:
        """综合检索日记 + 经验 + 知识，返回去重后的 top-k 条目列表

        每个条目格式：{"source": "diary"|"experience"|"knowledge", "date": str, "content": str, "score": float}
        """
        results: list[dict] = []
        results.extend(self.retrieve_diary(query, max_entries * 2))
        results.extend(self.retrieve_experience(query, max_entries))
        results.extend(self.retrieve_knowledge(query, max_entries))
        results.sort(key=lambda r: r["score"], reverse=True)
        return self._dedup(results, max_entries)

    def retrieve_diary(self, query: str, top_k: int = 5) -> list[dict]:
        """仅检索日记"""
        return self._search_dir(self.diary_dir, query, top_k, "diary")

    def retrieve_experience(self, query: str, top_k: int = 5) -> list[dict]:
        """仅检索个人经验"""
        return self._search_dir(self.experience_dir, query, top_k, "experience")

    def retrieve_knowledge(self, query: str, top_k: int = 5) -> list[dict]:
        """仅检索知识库（从 GitHub 学来的结构化知识）"""
        return self._search_dir(self.knowledge_dir, query, top_k, "knowledge")

    # ── 内部方法 ──

    def _search_dir(
        self, directory: Path, query: str, top_k: int, source: str
    ) -> list[dict]:
        """搜索目录下所有 .md 文件（knowledge 目录递归搜索子目录）"""
        if not directory.exists():
            return []

        query_terms = _tokenize(query)
        if not query_terms:
            return []

        scored: list[dict] = []
        # knowledge 目录有子文件夹结构，需要递归
        pattern = "**/*.md" if source == "knowledge" else "*.md"
        for md_file in sorted(directory.glob(pattern), reverse=True):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            entries = _parse_diary_entries(content)
            date_str = _extract_date(md_file.name)
            # knowledge 文件从文件头提取日期
            if source == "knowledge" and not date_str:
                date_str = _extract_date_from_header(content)
            for entry in entries:
                s = _score(query_terms, entry)
                if s >= self.MIN_SCORE:
                    scored.append({
                        "source": source,
                        "date": date_str,
                        "content": f"{entry['title']}\n{entry['body'][:500]}",
                        "score": round(s, 3),
                    })

        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    def _dedup(self, results: list[dict], max_entries: int) -> list[dict]:
        """按内容相似度去重，保留分数更高的"""
        keep: list[dict] = []
        for r in results:
            if len(keep) >= max_entries:
                break
            is_dup = any(
                _jaccard_similarity(r["content"], k["content"]) > self.DEDUP_THRESHOLD
                for k in keep
            )
            if not is_dup:
                keep.append(r)
        return keep


def _extract_date(filename: str) -> str:
    """从文件名提取日期，如 20260805.md → 2026-08-05"""
    m = re.match(r"(\d{4})(\d{2})(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _extract_date_from_header(content: str) -> str:
    """从知识文件头提取日期，匹配 '学习时间：YYYY-MM-DD'"""
    m = re.search(r"学习时间[：:]\s*(\d{4}-\d{2}-\d{2})", content)
    if m:
        return m.group(1)
    return ""
