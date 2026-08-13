#!/usr/bin/env python3
"""智序者 · 秩序分下降检测与经验强化归因

从 CHANGELOG 的 zx-meta 记录中检测秩序失效信号（返工/踩坑/回归/规范违规），
对违规记录抽取教训、匹配经验库，生成"经验强化任务单"（.runtime/evolution_tickets.jsonl）。

任务单分三类动作（不自动改写经验内容，灵魂层私有资产需谨慎）：
  - backfill：经验库无此教训（相似度 < backfill_threshold）→ 建议补记
  - promote ：教训已存在但没生效（相似度 >= rewrite_threshold）→ 建议强化检索加权（Phase 2 自动执行）
  - rewrite ：经验相关但不准确（相似度介于两阈值之间）→ 建议改写

用法：
  python scripts/evolve_check.py
  （通常由 order_score.py --history 在算分后自动附带调用）

退出码：0 = 正常；1 = 无法读取 CHANGELOG。
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 项目根（脚本位于 <root>/scripts/）
ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
STATE_FILE = ROOT / ".runtime" / "order_state.jsonl"
TICKET_FILE = ROOT / ".runtime" / "evolution_tickets.jsonl"

# 教训抽取关键词（正文中命中即视为"教训段落"候选）
LESSON_KEYWORDS = ("教训", "踩坑", "根因", "复发", "坑")

# 从 engine 读 evolution 配置（config 加载不触发模型下载，安全）
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from engine.config import config  # noqa: E402


# ── 轻量分词与相似度（独立实现，避免加载语义检索模型）──

def _tokenize(text: str) -> set[str]:
    """字符级 bigram（中文）+ 英文单词，用于经验匹配的轻量相似度。"""
    tokens: set[str] = set()
    cn = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for i in range(len(cn) - 1):
        tokens.add(cn[i : i + 2])
    for w in re.findall(r"[a-zA-Z]{2,}", text.lower()):
        tokens.add(w)
    return tokens


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ── 经验库读取 ──

def _split_h2(text: str) -> list[dict]:
    """按 ## 二级标题分段（经验/日记条目解析）。"""
    entries: list[dict] = []
    lines = text.split("\n")
    cur_title, cur_body = "", []
    started = False
    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            if started and cur_body:
                entries.append({"title": cur_title, "body": "\n".join(cur_body).strip()})
            started = True
            cur_title = line[3:].strip()
            cur_body = []
        elif started:
            cur_body.append(line)
    if started and cur_body:
        entries.append({"title": cur_title, "body": "\n".join(cur_body).strip()})
    return entries


def _load_experiences() -> list[dict]:
    """读取 memory/experience/ 下所有经验条目，返回 [{file, title, body}]。"""
    exp_dir = ROOT / "memory" / "experience"
    exps: list[dict] = []
    if not exp_dir.exists():
        return exps
    for f in sorted(exp_dir.glob("*.md"), reverse=True):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for e in _split_h2(text):
            exps.append({"file": f.name, "title": e["title"], "body": e["body"]})
    return exps


# ── 教训抽取 ──

def _extract_lesson(body: str) -> str:
    """从变更记录正文抽取教训文本（命中关键词的段落优先，否则回退标题摘要）。"""
    blocks = re.split(r"\n\s*\n", body)
    candidates = []
    for b in blocks:
        if any(k in b for k in LESSON_KEYWORDS):
            # 去掉 markdown 标题行（### 教训 / **教训** 等标记），保留实质内容
            lines = [l for l in b.splitlines() if not l.strip().startswith("#")]
            cleaned = "\n".join(lines).strip()
            if cleaned:
                candidates.append(cleaned)
    if candidates:
        return "\n".join(candidates)[:500]
    return body.strip()[:200]


# ── 违规归因 ──

def _violation_trigger(meta: dict) -> str | None:
    """从 meta 判定违规触发类型（按严重度优先级），无违规返回 None。"""
    if _to_bool(meta.get("recur")):
        return "recur"
    if _to_int(meta.get("regression")) > 0:
        return "regression"
    if _to_bool(meta.get("rework")):
        return "rework"
    if not _to_bool(meta.get("norm_ok")):
        return "norm_violation"
    return None


def _to_bool(val) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes", "y")


def _to_int(val) -> int:
    try:
        return int(str(val).strip())
    except (ValueError, AttributeError):
        return 0


def _decide_action(similarity: float, cfg) -> str:
    """按经验相似度决定强化动作。"""
    if similarity < cfg.backfill_threshold:
        return "backfill"
    if similarity >= cfg.rewrite_threshold:
        return "promote"
    return "rewrite"


def _read_tickets() -> list[dict]:
    if not TICKET_FILE.exists():
        return []
    tickets = []
    for line in TICKET_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            tickets.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return tickets


def _build_suggestion(action: str, lesson: str, sim: float | None, target: dict | None) -> str:
    if action == "backfill":
        return f"补记经验：**场景**<本次变更>；**教训**{lesson[:150]}"
    if action == "promote":
        ref = target["file"] if target else "经验库"
        return f"教训已存在（相似度 {sim:.2f}），建议强化检索加权 → {ref}"
    return f"经验相关但不完整，建议改写为：{lesson[:150]}"


def run_check(root: Path = ROOT, records: list[dict] | None = None) -> int:
    """执行秩序分下降检测与任务单生成，返回生成的 ticket 数。

    Args:
        root: 项目根（用于定位经验库/任务单文件）。
        records: 已解析的带 zx-meta 变更记录；为 None 时自行解析 CHANGELOG。
                 order_score 调用时传入已解析结果，避免重复解析与循环导入。
    """
    cfg = config.evolution
    if not cfg.enabled:
        return 0

    if records is None:
        # 独立运行时才延迟导入 order_score（此时非 __main__，无双重加载）
        from order_score import parse_records

        try:
            text = CHANGELOG.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[evolve_check] 无法读取 CHANGELOG: {exc}", file=sys.stderr)
            return 0
        records = parse_records(text)

    # CHANGELOG 记录为倒序（最新在前），取最近窗口
    total = len(records)
    window = records[: cfg.window_size]

    if total < cfg.min_entries:
        print(f"[evolve_check] 样本不足（{total} < {cfg.min_entries}），跳过检测")
        return 0

    # 防抖/冷却：已有 pending 任务单时，若记录增长不足 cooldown，跳过
    existing = _read_tickets()
    pending = [t for t in existing if t.get("status") == "pending"]
    if pending:
        last_total = max(t.get("window_total", 0) for t in pending)
        if total - last_total < cfg.cooldown_entries:
            print(f"[evolve_check] 冷却中（新记录 {total - last_total} < {cfg.cooldown_entries}），跳过")
            return 0

    # 已有任务单的 (title, trigger) 集合，用于防抖去重
    seen_keys = {(t.get("changelog_title"), t.get("trigger")) for t in pending}

    experiences = _load_experiences()
    new_tickets = 0

    for rec in window:
        trigger = _violation_trigger(rec["meta"])
        if trigger is None:
            continue
        key = (rec["title"], trigger)
        if key in seen_keys:
            continue

        lesson = _extract_lesson(rec["body"])
        # 匹配经验库 top1
        best, best_sim = None, 0.0
        for e in experiences:
            sim = _jaccard(lesson, e["body"])
            if sim > best_sim:
                best_sim, best = sim, e

        action = _decide_action(best_sim, cfg)
        ticket = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "trigger": trigger,
            "window_total": total,
            "changelog_title": rec["title"],
            "lesson": lesson[:300],
            "action": action,
            "auto": action == "promote",  # promote 仅加权重，Phase 2 自动执行
            "similarity": round(best_sim, 3),
            "target_experience": (best["file"] + " :: " + best["title"][:80]) if best else None,
            "suggestion": _build_suggestion(action, lesson, best_sim, best),
            "status": "pending",
        }
        _append_ticket(ticket)
        new_tickets += 1
        seen_keys.add(key)

    if new_tickets:
        print(f"[evolve_check] 生成 {new_tickets} 张经验强化任务单 → {TICKET_FILE}")
    else:
        print("[evolve_check] 无新秩序失效信号，未生成任务单")
    return new_tickets


def _append_ticket(ticket: dict) -> None:
    TICKET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TICKET_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(ticket, ensure_ascii=False) + "\n")


def main() -> int:
    run_check(ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
