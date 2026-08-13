"""order_score.py 单元测试 —— 秩序分度量核心逻辑

覆盖：记录级解析（标题↔zx-meta 关联、示例块跳过）、
秩序分计算（四子指标 + 综合分 + 违规归因）、类型转换、报告格式化。
"""

import sys
from pathlib import Path

import pytest

# 项目根 + scripts 目录（order_score.py 是独立脚本，不在 engine 包内）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_PROJECT_ROOT, _PROJECT_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import order_score


def _record(title="记录", rework=False, recur=False, regression=0, norm_ok=True, type_="fix"):
    """构造一条带 meta 的变更记录（meta 值为字符串，模拟解析结果）。"""
    return {
        "title": title,
        "meta": {
            "type": type_,
            "rework": str(rework).lower(),
            "recur": str(recur).lower(),
            "regression": str(regression),
            "norm_ok": str(norm_ok).lower(),
        },
        "body": "",
    }


# ── 解析 ──

def test_parse_records_single():
    text = (
        "## [2026-08-13] v1.7.0 测试记录\n\n"
        "<!-- zx-meta\ntype: feat\nrework: false\nrecur: false\nregression: 0\nnorm_ok: true\n-->\n\n"
        "### 需求背景\nxxx\n"
    )
    records = order_score.parse_records(text)
    assert len(records) == 1
    assert records[0]["meta"]["type"] == "feat"
    assert "测试记录" in records[0]["title"]


def test_parse_records_skips_no_meta():
    text = (
        "## 版号规范（无 meta）\n\n这是说明文字\n\n"
        "## [2026-08-13] v1.7.0 有meta\n\n"
        "<!-- zx-meta\ntype: feat\n-->\n\nbody\n"
    )
    records = order_score.parse_records(text)
    assert len(records) == 1
    assert "有meta" in records[0]["title"]


def test_parse_records_skips_code_fence():
    # 代码围栏内的 zx-meta 示例块不参与统计（示例 ≠ 真实记录）
    text = (
        "## 规范区\n\n"
        "```html\n<!-- zx-meta\ntype: feat\nrework: false\n-->\n```\n\n"
    )
    records = order_score.parse_records(text)
    assert records == []


def test_parse_meta_body_defaults():
    # 缺省字段自动补齐为"良好状态"
    meta = order_score._parse_meta_body("<!-- zx-meta\ntype: fix\n-->")
    assert meta == {
        "type": "fix",
        "rework": "false",
        "recur": "false",
        "regression": "0",
        "norm_ok": "true",
    }


# ── 类型转换 ──

def test_to_bool():
    assert order_score._to_bool("true") is True
    assert order_score._to_bool("True") is True
    assert order_score._to_bool("false") is False
    assert order_score._to_bool("yes") is True


def test_to_int():
    assert order_score._to_int("3") == 3
    assert order_score._to_int("abc") == 0
    assert order_score._to_int(None) == 0


# ── 秩序分计算 ──

def test_compute_order_score_perfect():
    records = [_record(f"r{i}") for i in range(5)]
    result = order_score.compute_order_score(records)
    assert result["total"] == 5
    assert result["order_score"] == pytest.approx(1.0)
    assert result["violations"] == []
    assert result["recur_count"] == 0


def test_compute_order_score_with_violations():
    records = [
        _record("r1"),                      # 良好
        _record("r2", recur=True),          # 踩坑
        _record("r3", rework=True),         # 返工
        _record("r4", regression=2),        # 回归
        _record("r5", norm_ok=False),       # 规范违规
    ]
    result = order_score.compute_order_score(records)
    # R=0.2 D=0.2 B=0.2 (1-C)=0.2 → O = 1 - 0.25*0.8 = 0.8
    assert result["order_score"] == pytest.approx(0.8)
    assert len(result["violations"]) == 4
    assert result["recur_count"] == 1
    assert result["norm_ok_count"] == 4


def test_compute_order_score_empty():
    result = order_score.compute_order_score([])
    assert result["total"] == 0
    assert result["order_score"] is None
    assert result["violations"] == []


def test_compute_order_score_type_dist():
    records = [
        _record("r1", type_="feat"),
        _record("r2", type_="feat"),
        _record("r3", type_="fix"),
    ]
    result = order_score.compute_order_score(records)
    assert result["type_dist"] == {"feat": 2, "fix": 1}


# ── 报告格式化 ──

def test_format_report_empty():
    report = order_score.format_report(order_score.compute_order_score([]))
    assert "无元数据" in report or "尚未发现" in report


def test_format_report_contains_fields():
    result = order_score.compute_order_score([_record("r1")])
    report = order_score.format_report(result)
    assert "返工率" in report
    assert "秩序分" in report
    assert "1.000" in report
