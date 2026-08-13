#!/usr/bin/env python3
"""智序者 · 秩序分扫描器

扫描 CHANGELOG.md 中的 zx-meta 元数据块，计算秩序分的四个子指标
（返工率 R / 重复踩坑率 D / 回归率 B / 规范遵循率 C）与综合秩序分 O。

秩序分是自进化目标函数的第一维（秩序维），用于度量"秩序是否真的
阻止了返工、踩坑、回归"。跨时间追踪秩序分的趋势即可判断系统是否在
稳定地变好——而非仅仅"做了很多事"。

用法：
  python scripts/order_score.py [path/to/CHANGELOG.md] [--history]

  --history  将本次扫描结果追加写入 .runtime/order_state.jsonl
             （时序落盘，供 evolve_check.py 做秩序分下降检测与归因），
             并在算分后自动附带秩序分下降检测（若 config.evolution.enabled）。

默认扫描 <root>/CHANGELOG.md，输出各子指标与秩序分到控制台。
退出码：0 = 正常（含"无元数据"提示）；1 = 文件不存在或无法读取。
"""

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# 项目根（脚本位于 <root>/scripts/）
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"

# .runtime 是私有运行目录（已被 .gitignore 隔离）
STATE_FILE = ROOT / ".runtime" / "order_state.jsonl"

# zx-meta 块正则：<!-- zx-meta ... -->（跨行，非贪婪，兼容 HTML 注释）
META_BLOCK_RE = re.compile(r"<!--\s*zx-meta\b(.*?)-->", re.DOTALL)

# Markdown 代码围栏：规范区的示例块不参与统计（示例 ≠ 真实变更记录）
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# 二级标题（变更记录边界；### 三级标题不算记录，靠 startswith 精确区分）
H2_RE = re.compile(r"^##\s+")

# 秩序分子指标权重（各 0.25，和为 1）
WEIGHTS = {
    "rework": 0.25,        # 返工率 R
    "recur": 0.25,         # 重复踩坑率 D
    "regression": 0.25,    # 回归率 B
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

# 判定"违规"的字段（用于归因：这些字段为 true/正数即视为秩序失效信号）
VIOLATION_FIELDS = ("rework", "recur", "regression", "norm_ok")


def _parse_meta_body(body: str) -> dict | None:
    """从单条记录正文中提取 zx-meta 字段 dict（缺省值补齐），无则返回 None。"""
    match = META_BLOCK_RE.search(body)
    if not match:
        return None
    entry = dict(DEFAULTS)
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        if key in entry:
            entry[key] = val.strip()
    return entry


def parse_records(text: str) -> list[dict]:
    """按二级标题分段，解析出带 zx-meta 的变更记录。

    返回 [{title, meta, body}]，仅包含真正带 zx-meta 的记录；
    无 zx-meta 的标题（版号规范、旧记录）自动跳过。
    """
    # 代码围栏内的示例块（如版号规范区的 zx-meta 示例）不参与统计
    text = CODE_FENCE_RE.sub("", text)

    records: list[dict] = []
    lines = text.split("\n")
    current_title = ""
    current_body: list[str] = []
    started = False

    def flush():
        if not started or not current_title:
            return
        body = "\n".join(current_body).strip()
        meta = _parse_meta_body(body)
        if meta is not None:
            records.append({"title": current_title, "meta": meta, "body": body})

    for line in lines:
        if H2_RE.match(line):
            flush()
            started = True
            current_title = line[2:].strip()
            current_body = []
        elif started:
            current_body.append(line)
    flush()
    return records


def _to_bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes", "y")


def _to_int(val: str) -> int:
    try:
        return int(str(val).strip())
    except (ValueError, AttributeError):
        return 0


def compute_order_score(records: list[dict]) -> dict:
    """根据变更记录（含 meta）计算秩序分四子指标与综合分，返回结果 dict。"""
    n = len(records)
    if n == 0:
        return {
            "total": 0,
            "rework_rate": None,
            "recur_rate": None,
            "regression_rate": None,
            "norm_rate": None,
            "order_score": None,
            "type_dist": {},
            "violations": [],
        }

    rework = sum(1 for r in records if _to_bool(r["meta"]["rework"]))
    recur = sum(1 for r in records if _to_bool(r["meta"]["recur"]))
    regression = sum(1 for r in records if _to_int(r["meta"]["regression"]) > 0)
    norm_ok = sum(1 for r in records if _to_bool(r["meta"]["norm_ok"]))

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

    type_dist = dict(Counter(r["meta"]["type"] for r in records))

    # 归因所需的违规记录清单（任一违规字段命中即收录）
    violations = []
    for r in records:
        if (
            _to_bool(r["meta"]["rework"])
            or _to_bool(r["meta"]["recur"])
            or _to_int(r["meta"]["regression"]) > 0
            or not _to_bool(r["meta"]["norm_ok"])
        ):
            violations.append({"title": r["title"], "meta": r["meta"]})

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
        "violations": violations,
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
    for t, cnt in result["type_dist"].items():
        if t not in TYPE_ORDER:
            lines.append(f"  {t:<8} {cnt}")
    return "\n".join(lines)


def append_history(result: dict, path: Path = STATE_FILE) -> None:
    """把本次扫描结果追加到 .runtime/order_state.jsonl（时序落盘）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "total": result["total"],
        "order_score": result["order_score"],
        "rework_count": result.get("rework_count", 0),
        "recur_count": result.get("recur_count", 0),
        "regression_count": result.get("regression_count", 0),
        "norm_ok_count": result.get("norm_ok_count", 0),
        "violations": result.get("violations", []),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    args = [a for a in sys.argv[1:]]
    do_history = "--history" in args
    args = [a for a in args if a != "--history"]

    path = Path(args[0]) if args else DEFAULT_CHANGELOG
    if not path.is_file():
        print(f"❌ 找不到文件: {path}", file=sys.stderr)
        return 1

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"❌ 读取失败: {path} → {exc}", file=sys.stderr)
        return 1

    records = parse_records(text)
    result = compute_order_score(records)
    print(format_report(result))

    if do_history:
        append_history(result)
        print(f"\n[order_score] 已落盘时序快照 → {STATE_FILE}")

        # 自动附带秩序分下降检测（若启用）
        try:
            from evolve_check import run_check
            run_check(ROOT)
        except Exception as exc:  # 检测失败绝不影响算分主流程
            print(f"[order_score] 秩序分下降检测跳过: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
