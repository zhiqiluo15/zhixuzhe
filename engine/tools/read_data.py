"""数据读取工具 —— 读取 CSV / JSON / JSONL 并输出结构预览与统计摘要

零依赖实现：csv / json / statistics 标准库。
适合"数据分析"场景的第一步：了解数据长什么样（列、类型、规模、分布），
Brain 基于该摘要做进一步分析，无需把原始数据全部塞进上下文。

设计约束（沿用 file_io 边界约定）：
- 路径限制在项目根目录内，越界拒绝
- 二进制检测 + 文件大小上限 + 统计行数上限，防止撑爆上下文
"""

import csv
import io
import json
import statistics
from pathlib import Path

from engine.config import config

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 文件大小上限（10MB）
MAX_FILE_BYTES = 10 * 1024 * 1024
# 统计最多扫描行数（样本足够代表性即可）
MAX_STAT_ROWS = 10_000
# 预览最多行数
MAX_PREVIEW_ROWS = 50
# 文本预览最多字符
MAX_TEXT_CHARS = 4000
# 单个单元格预览最多字符
MAX_CELL_CHARS = 60


def _resolve_path(filepath: str) -> Path:
    """解析路径。相对路径相对于项目根。"""
    p = Path(filepath)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return p.resolve()


def _fmt(v, max_chars: int = MAX_CELL_CHARS) -> str:
    """格式化单元格值，超长截断。"""
    s = str(v)
    if len(s) > max_chars:
        s = s[:max_chars] + "…"
    return s


def _is_numeric(values: list) -> tuple[bool, list]:
    """判断一列是否为数值列（可转 float 的比例 >= 80%），返回 (is_numeric, float_values)"""
    floats = []
    converted = 0
    for v in values:
        if v is None or v == "":
            continue
        try:
            floats.append(float(v))
            converted += 1
        except (TypeError, ValueError):
            floats.append(None)
    total = len(values)
    if total == 0:
        return False, []
    return (converted / total) >= 0.8, [f for f in floats if f is not None]


def _describe_numeric(values: list[float]) -> str:
    """数值列统计摘要。"""
    n = len(values)
    parts = [f"count={n}"]
    if n:
        parts.append(f"min={min(values):g}")
        parts.append(f"max={max(values):g}")
        parts.append(f"mean={statistics.fmean(values):.4g}")
        if n >= 2:
            parts.append(f"std={statistics.stdev(values):.4g}")
    return ", ".join(parts)


def _describe_categorical(values: list) -> str:
    """类别列统计摘要：唯一值数量 + top 3 频次。"""
    n = len(values)
    counter: dict[str, int] = {}
    for v in values:
        key = "None" if v is None else str(v)
        counter[key] = counter.get(key, 0) + 1
    uniq = len(counter)
    top = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    top_str = ", ".join(f"{_fmt(k)}×{c}" for k, c in top)
    return f"unique={uniq}, top: {top_str} (n={n})"


def _analyze_rows(rows: list[dict]) -> str:
    """对列表型数据（list[dict]）做结构分析与统计。"""
    if not rows:
        return "数据为空（0 行）"

    # 列名（保序取并集）
    columns: list[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)

    lines = [f"数据规模: {len(rows)} 行 × {len(columns)} 列"]
    lines.append(f"列名: {', '.join(columns)}")

    # 按列统计
    for col in columns:
        values = [r.get(col) for r in rows[:MAX_STAT_ROWS]]
        num, floats = _is_numeric(values)
        if num:
            lines.append(f"  [{col}] 数值列 — {_describe_numeric(floats)}")
        else:
            lines.append(f"  [{col}] 类别列 — {_describe_categorical(values)}")

    return "\n".join(lines)


def _preview_rows(rows: list[dict], preview_rows: int) -> str:
    """前 N 行预览（表格样式）。"""
    if not rows:
        return "（无数据）"
    columns: list[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)

    lines = []
    for i, r in enumerate(rows[:preview_rows], 1):
        cells = [f"{_fmt(r.get(c))}" for c in columns]
        lines.append(f"  R{i}: {', '.join(cells)}")
    return "\n".join(lines)


def read_data(filepath: str, format: str = "auto", preview_rows: int = 10) -> str:
    """读取数据文件，输出结构预览与统计摘要。

    Args:
        filepath: 文件路径（相对项目根或绝对路径）
        format: 数据格式，auto 按扩展名推断（csv/json/jsonl/text）
        preview_rows: 预览行数（默认 10，上限 50）

    Returns:
        结构化的数据摘要文本
    """
    path = _resolve_path(filepath)
    try:
        path.relative_to(_PROJECT_ROOT)
    except ValueError:
        return f"错误: 文件不在项目目录内 — {filepath}"
    if not path.exists():
        return f"错误: 文件不存在 — {filepath}"
    if path.is_dir():
        return f"错误: 路径是目录而非文件 — {filepath}"

    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return f"错误: 文件过大（>{MAX_FILE_BYTES//1024//1024}MB），无法读取 — {filepath}"
    except OSError as e:
        return f"读取失败: {e}"

    # 二进制检测
    try:
        with open(path, "rb") as bf:
            head = bf.read(2048)
        if b"\x00" in head:
            return f"错误: 文件为二进制格式，无法以文本读取 — {filepath}"
    except Exception as e:
        return f"读取失败: {e}"

    # 格式推断
    fmt = format.strip().lower() if format and format.strip() else "auto"
    if fmt == "auto":
        fmt = path.suffix.lower().lstrip(".")
    if fmt not in ("csv", "json", "jsonl", "text", "txt"):
        return f"错误: 不支持的数据格式 '{fmt}'（支持 csv/json/jsonl/text）"

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"读取失败: {e}"

    preview_rows = max(1, min(preview_rows, MAX_PREVIEW_ROWS))

    # ── CSV ──
    if fmt == "csv":
        try:
            reader = csv.DictReader(io.StringIO(text))
            rows = []
            for i, r in enumerate(reader):
                if i >= MAX_STAT_ROWS:
                    break
                rows.append({k: v for k, v in r.items()})
        except Exception as e:
            return f"CSV 解析失败: {e}"
        header = f"文件: {path.relative_to(_PROJECT_ROOT)}（CSV，共读入 {len(rows)} 行统计）"
        return f"{header}\n\n{_analyze_rows(rows)}\n\n前 {min(preview_rows, len(rows))} 行预览:\n{_preview_rows(rows, preview_rows)}"

    # ── JSON ──
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return f"JSON 解析失败: {e}"
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            rows = [r for r in data[:MAX_STAT_ROWS]]
            header = f"文件: {path.relative_to(_PROJECT_ROOT)}（JSON 数组，共 {len(data)} 条记录）"
            return f"{header}\n\n{_analyze_rows(rows)}\n\n前 {min(preview_rows, len(rows))} 行预览:\n{_preview_rows(rows, preview_rows)}"
        if isinstance(data, dict):
            lines = [f"文件: {path.relative_to(_PROJECT_ROOT)}（JSON 对象，{len(data)} 个顶层键）"]
            for k, v in data.items():
                vtype = type(v).__name__
                if isinstance(v, list):
                    lines.append(f"  {k}: list[{len(v)}]")
                elif isinstance(v, dict):
                    lines.append(f"  {k}: dict[{len(v)}]")
                else:
                    lines.append(f"  {k}: {vtype} = {_fmt(v)}")
            return "\n".join(lines)
        return f"文件: {path.relative_to(_PROJECT_ROOT)}（JSON 标量）\n值: {_fmt(data, 2000)}"

    # ── JSONL ──
    if fmt == "jsonl":
        rows = []
        for i, line in enumerate(text.splitlines()):
            if i >= MAX_STAT_ROWS:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
        if not rows:
            return f'文件: {path.relative_to(_PROJECT_ROOT)}（JSONL，无可解析对象）'
        header = f"文件: {path.relative_to(_PROJECT_ROOT)}（JSONL，共读入 {len(rows)} 条统计）"
        return f"{header}\n\n{_analyze_rows(rows)}\n\n前 {min(preview_rows, len(rows))} 行预览:\n{_preview_rows(rows, preview_rows)}"

    # ── TEXT ──
    lines_all = text.splitlines()
    header = f"文件: {path.relative_to(_PROJECT_ROOT)}（文本，共 {len(lines_all)} 行，{len(text)} 字符）"
    preview = "\n".join(f"  L{i}: {_fmt(l, 200)}" for i, l in enumerate(lines_all[:preview_rows], 1))
    return f"{header}\n\n前 {min(preview_rows, len(lines_all))} 行:\n{preview}"
