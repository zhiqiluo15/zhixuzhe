"""evolve_check.py 单元测试 —— 秩序分下降检测核心逻辑

覆盖：轻量分词/Jaccard、经验条目分段、教训抽取（剥离标题）、
违规归因、动作阈值分流、建议构建。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# 项目根 + scripts 目录（evolve_check.py 是独立脚本，不在 engine 包内）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_PROJECT_ROOT, _PROJECT_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import evolve_check


def _cfg(backfill=0.3, rewrite=0.6):
    return SimpleNamespace(backfill_threshold=backfill, rewrite_threshold=rewrite)


# ── 分词与相似度 ──

def test_tokenize_cn_en():
    tokens = evolve_check._tokenize("部署进程 restart")
    assert "部署" in tokens   # 中文 2-gram
    assert "restart" in tokens  # 英文单词


def test_jaccard_identical():
    assert evolve_check._jaccard("部署后必须重启进程", "部署后必须重启进程") == pytest.approx(1.0)


def test_jaccard_unrelated():
    assert evolve_check._jaccard("部署进程", "天气查询") == 0.0


def test_jaccard_partial():
    sim = evolve_check._jaccard("部署后必须重启进程", "部署后需要重启进程")
    assert 0.0 < sim < 1.0


# ── 经验条目分段 ──

def test_split_h2():
    text = "## 条目1\n内容A\n\n## 条目2\n内容B\n"
    entries = evolve_check._split_h2(text)
    assert len(entries) == 2
    assert entries[0]["title"] == "条目1"
    assert entries[1]["title"] == "条目2"
    assert "内容A" in entries[0]["body"]


def test_split_h2_skips_subheading():
    text = "## 条目1\n内容\n### 子标题\n子内容\n"
    entries = evolve_check._split_h2(text)
    assert len(entries) == 1  # ### 三级标题不构成新条目
    assert "### 子标题" in entries[0]["body"]


# ── 教训抽取 ──

def test_extract_lesson_strips_heading():
    body = "### 需求背景\nxxx\n\n### 教训\n部署后必须重启进程\n\n### 验证\n通过"
    lesson = evolve_check._extract_lesson(body)
    assert "部署后必须重启进程" in lesson
    assert "###" not in lesson  # markdown 标题被剥离


def test_extract_lesson_fallback():
    body = "这是正文内容，没有教训关键词"
    lesson = evolve_check._extract_lesson(body)
    assert lesson == body


# ── 违规归因 ──

def test_violation_trigger_priority():
    # recur 优先级最高（即使同时有 rework）
    meta = {"recur": "true", "rework": "true", "regression": "0", "norm_ok": "true"}
    assert evolve_check._violation_trigger(meta) == "recur"


def test_violation_trigger_all_types():
    assert evolve_check._violation_trigger({"recur": "false", "rework": "false", "regression": "2", "norm_ok": "true"}) == "regression"
    assert evolve_check._violation_trigger({"recur": "false", "rework": "true", "regression": "0", "norm_ok": "true"}) == "rework"
    assert evolve_check._violation_trigger({"recur": "false", "rework": "false", "regression": "0", "norm_ok": "false"}) == "norm_violation"


def test_violation_trigger_none():
    assert evolve_check._violation_trigger({"recur": "false", "rework": "false", "regression": "0", "norm_ok": "true"}) is None


# ── 动作阈值分流 ──

def test_decide_action():
    cfg = _cfg()
    assert evolve_check._decide_action(0.1, cfg) == "backfill"
    assert evolve_check._decide_action(0.5, cfg) == "rewrite"
    assert evolve_check._decide_action(0.8, cfg) == "promote"
    # 边界值
    assert evolve_check._decide_action(0.3, cfg) == "rewrite"  # 恰好等于 backfill 阈值 → rewrite 区间
    assert evolve_check._decide_action(0.6, cfg) == "promote"  # 恰好等于 rewrite 阈值 → promote


# ── 建议构建 ──

def test_build_suggestion_backfill():
    s = evolve_check._build_suggestion("backfill", "教训内容", 0.1, None)
    assert "补记经验" in s


def test_build_suggestion_promote():
    s = evolve_check._build_suggestion("promote", "教训内容", 0.8, {"file": "20260813.md"})
    assert "强化检索加权" in s
    assert "20260813.md" in s


def test_build_suggestion_rewrite():
    s = evolve_check._build_suggestion("rewrite", "教训内容", 0.5, None)
    assert "改写为" in s
