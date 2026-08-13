#!/usr/bin/env python3
"""智序者 · 秩序分扫描器

扫描 CHANGELOG.md 中的 zx-meta 元数据块，计算秩序分的四个子指标
（返工率 R / 重复踩坑率 D / 回归率 B / 规范遵循率 C）与综合秩序分 O。

秩序分是自进化目标函数的第一维（秩序维），用于度量"秩序是否真的
阻止了返工、踩坑、回归"。跨时间追踪秩序分的趋势即可判断系统是否在
稳定地变好——而非仅仅"做了很多事"。

用法：
  python scripts/order_score.py [path/to/CHANGELOG.md]

默认扫描 <root>/CHANGELOG.md，输出各子指标与秩序分到控制台。
退出码：0 = 正常（含"无元数据"提示）；1 = 文件不存在或无法读取。
"""

import re
import sys
from collections import Counter
from pathlib import Path

# 项目根（脚本位于 <root>/scripts/）
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"

# zx-meta 块正则：<!-- zx-meta ... -->（跨行，非贪婪，兼容 HTML 注释）
META_BLOCK_RE = re.compile(r"<!--\s*zx-meta\b(.*?)-->", re.DOTALL)

# Markdown 代码围栏：规范区的示例块不参与统计（示例 ≠ 真实变更记录）
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# 秩序分子指标权重（各 0.25，和为 1）
WEIGHTS = {
    "rework": 0.25,       # 返工率 R
    "recur": 0.25,        # 重复踩坑率 D
    "regression": 0.25,   # 回归率 B
    "norm_violation": 0.25,  # 规范违规率 (1 - C)
}

# 字段缺省值（缺省 = 良好状态，违规才需显式标记）
DEFAULTS = {
    "type": "unknown",
    "rework": "false",
    "recur": "false",
    "regression": "0",
    "norm_ok": "true",
}

# 合法的 type 取值（用于分类统计排序展示）
TYPE_ORDER = ("feat", "fix", "refactor", "docs", "revert", "unknown")


def parse_meta(text: str) -> list[dict]:
    """解析文本中的全部 zx-meta 块，返回字段 dict 列表（缺省值已补齐）。"""
    entries = []
    for match in META_BLOCK_RE.finditer(text):
        body = match.group(1)
        entry = dict(DEFAULTS)
        for line in body.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            if key in entry:
                entry[key] = val.strip()
        entries.append(entry)
    return entries


def _to_bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes", "y")


def _to_int(val: str) -> int:
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return 0


def compute_order_score(entries: list[dict]) -> dict:
    """根据元数据条目计算秩序分四子指标与综合分，返回结果 dict。"""
    n = len(entries)
    if n == 0:
        return {
            "total": 0,
            "rework_rate": None,
            "recur_rate": None,
            "regression_rate": None,
            "norm_rate": None,
            "order_score": None,
            "type_dist": {},
        }

    rework = sum(1 for e in entries if _to_bool(e["rework"]))
    recur = sum(1 for e in entries if _to_bool(e["recur"]))
    regression = sum(1 for e in entries if _to_int(e["regression"]) > 0)
    norm_ok = sum(1 for e in entries if _to_bool(e["norm_ok"]))

    rework_rate = rework / n
    recur_rate = recur / n
    regression_rate = regression / n
    norm_rate = norm_ok / n
    norm_violation = 1 - norm_rate

    order_score = 1 - (
        WEIGHTS["rework"] * rework_rate
        + WEIGHTS["recur"] * recur_rate
        + WEIGHTS["regression"] * regression_rate
        + WEIGHTS["norm_violation"] * norm_violation
    )

    type_dist = dict(Counter(e["type"] for e in entries))

    return {
        "total": n,
        "rework_count": rework,
        "recur_count": recur,
        "regression_count": regression,
        "norm_ok_count": norm_ok,
        "rework_rate": rework_rate,
        "recur_rate": recur_rate,
        "regression_rate": regression_rate,
        "norm_rate": norm_rate,
        "order_score": order_score,
        "type_dist": type_dist,
    }


def format_report(result: dict) -> str:
    """将计算结果格式化为可读报告文本。"""
    if result["total"] == 0:
        return (
            "秩序分度量报告\n"
            "================\n"
            "尚未发现任何 zx-meta 元数据块，无法计算秩序分。\n"
            "请在 CHANGELOG 的变更记录标题正下方放置 zx-meta 块（见版号规范区）。\n"
        )

    lines = [
        "秩序分度量报告",
        "================",
        f"变更条目总数（含 zx-meta）: {result['total']}",
        "",
        f"返工率   R = {result['rework_count']}/{result['total']} = {result['rework_rate']:.2%}",
        f"重复踩坑 D = {result['recur_count']}/{result['total']} = {result['recur_rate']:.2%}",
        f"回归率   B = {result['regression_count']}/{result['total']} = {result['regression_rate']:.2%}",
        f"规范遵循 C = {result['norm_ok_count']}/{result['total']} = {result['norm_rate']:.2%}",
        "",
        f"秩序分   O = {result['order_score']:.3f}  （1.000 = 理想秩序，0.000 = 完全失序）",
        "",
        "变更类型分布:",
    ]
    for t in TYPE_ORDER:
        cnt = result["type_dist"].get(t, 0)
        if cnt:
            lines.append(f"  {t:<8} {cnt}")
    # 兜底：出现不在 TYPE_ORDER 中的未知类型
    for t, cnt in result["type_dist"].items():
        if t not in TYPE_ORDER:
            lines.append(f"  {t:<8} {cnt}")
    return "\n".join(lines)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CHANGELOG
    if not path.is_file():
        print(f"❌ 找不到文件: {path}", file=sys.stderr)
        return 1

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"❌ 读取失败: {path} → {exc}", file=sys.stderr)
        return 1

    # 代码围栏内的示例块（如版号规范区的 zx-meta 示例）不参与统计
    text = CODE_FENCE_RE.sub("", text)
    entries = parse_meta(text)
    result = compute_order_score(entries)
    print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
