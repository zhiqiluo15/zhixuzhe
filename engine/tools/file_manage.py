"""文件管理工具 —— 批量列出 / 重命名 / 移动 / 复制 / 删除 / 内容替换

两个函数：
- list_files: 只读，列出目录/glob 匹配的文件（名称 + 大小 + 修改时间）
- batch_files: 批量操作，默认 dry_run 预览，确认后才实际执行

安全设计（沿用 file_io 边界约定，且批量操作是破坏性动作，要求更高）：
- 所有路径限制在项目根目录内，越界拒绝
- 操作对象是 glob 匹配的文件，不递归删目录
- 默认 dry_run=True 只预览不执行；实际执行由调用方（react_loop HITL 确认）把关
- 单文件操作失败不中断整体，逐项记录并汇总
- 输出条数上限，防止撑爆上下文
"""

import os
import shutil
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 忽略目录（与 search_file 保持一致）
_IGNORE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", "node_modules",
    ".venv", "venv", "dist", "build", "target", ".cargo",
}

# 输出条数上限
MAX_LIST_ROWS = 200
MAX_OP_ROWS = 100

_ACTIONS = ("rename", "move", "copy", "delete", "replace")


def _resolve_path(path: str) -> Path:
    """解析路径。相对路径相对于项目根。"""
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return p.resolve()


def _fmt_size(n: int) -> str:
    """人类可读的文件大小。"""
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"


def list_files(path: str = ".", pattern: str = "*", recursive: bool = False) -> str:
    """列出目录下的文件（名称 + 大小 + 修改时间）。

    Args:
        path: 起始目录（相对项目根，默认项目根）
        pattern: 文件名 glob 过滤（如 "*.log"）
        recursive: 是否递归子目录

    Returns:
        文件清单文本
    """
    root = _resolve_path(path)
    try:
        root.relative_to(_PROJECT_ROOT)
    except ValueError:
        return f"错误: 路径不在项目目录内 — {path}"
    if not root.exists():
        return f"错误: 路径不存在 — {path}"

    if not pattern or not pattern.strip():
        pattern = "*"

    entries = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            for fname in filenames:
                if fnmatch(fname, pattern):
                    entries.append(Path(dirpath) / fname)
    else:
        for f in root.iterdir():
            if f.is_file() and fnmatch(f.name, pattern):
                entries.append(f)

    entries.sort(key=lambda p: str(p).lower())
    if len(entries) > MAX_LIST_ROWS:
        entries = entries[:MAX_LIST_ROWS]

    if not entries:
        return f"目录 {path} 下未找到匹配 '{pattern}' 的文件"

    lines = [f"目录 {path}（匹配 '{pattern}'，共 {len(entries)} 个文件）\n"]
    for f in entries:
        try:
            size = _fmt_size(f.stat().st_size)
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            size, mtime = "?", "?"
        rel = f.relative_to(_PROJECT_ROOT)
        lines.append(f"  {rel.as_posix()}  [{size}]  {mtime}")
    return "\n".join(lines)


def _match_files(pattern: str) -> tuple[list[Path], str]:
    """将 glob 模式解析为项目根内的文件列表。返回 (files, error)。"""
    if not pattern or not pattern.strip():
        return [], "错误: glob 匹配模式不能为空"

    p = Path(pattern)
    if p.is_absolute():
        try:
            p.relative_to(_PROJECT_ROOT)
        except ValueError:
            return [], f"错误: 匹配路径不在项目目录内 — {pattern}"
        matches = list(p.parent.glob(p.name)) if p.parent.is_dir() else []
    else:
        matches = list(_PROJECT_ROOT.glob(pattern))

    # 只保留文件，忽略目录；并跳过忽略目录内的文件
    files = []
    for m in matches:
        if not m.is_file():
            continue
        try:
            m.relative_to(_PROJECT_ROOT)
        except ValueError:
            continue
        if any(part in _IGNORE_DIRS for part in m.relative_to(_PROJECT_ROOT).parts):
            continue
        files.append(m)

    return files, ""


def batch_files(
    action: str,
    pattern: str,
    target: str = "",
    replace_from: str = "",
    replace_to: str = "",
    dry_run: bool = True,
) -> str:
    """批量文件操作（rename / move / copy / delete / replace）。

    Args:
        action: rename（文件名文本替换）/ move / copy / delete / replace（内容替换）
        pattern: 匹配文件的 glob 模式（相对项目根），如 "*.tmp"、"logs/*.log"
        target: move/copy 的目标目录（相对项目根）
        replace_from: rename 的文件名替换文本 / replace 的内容查找文本
        replace_to: 替换后的文本
        dry_run: True 只预览改动清单不执行（默认），False 实际执行

    Returns:
        操作结果文本
    """
    if action not in _ACTIONS:
        return f"错误: 不支持的操作 '{action}'（支持 {'/'.join(_ACTIONS)}）"

    files, err = _match_files(pattern)
    if err:
        return err
    if not files:
        return f'未找到匹配 "{pattern}" 的文件'

    # 参数校验
    if action == "rename" and not replace_from:
        return "错误: rename 需要 replace_from（文件名中要替换的文本）"
    if action == "replace" and not replace_from:
        return "错误: replace 需要 replace_from（要查找的内容）"
    if action in ("move", "copy") and not target.strip():
        return f"错误: {action} 需要 target（目标目录）"

    dest_dir = None
    if action in ("move", "copy"):
        dest_dir = _resolve_path(target)
        try:
            dest_dir.relative_to(_PROJECT_ROOT)
        except ValueError:
            return f"错误: 目标目录不在项目目录内 — {target}"

    if len(files) > MAX_OP_ROWS:
        files = files[:MAX_OP_ROWS]

    preview_lines = [f"[{action}] 将处理 {len(files)} 个文件（{pattern}）"]
    exec_lines = [f"[{action}] 处理 {len(files)} 个文件（{pattern}）"]
    errors: list[str] = []

    for f in files:
        rel = f.relative_to(_PROJECT_ROOT)

        if action == "rename":
            new_name = f.name.replace(replace_from, replace_to)
            new_path = f.with_name(new_name)
            if new_name == f.name:
                preview_lines.append(f"  跳过（名称无变化）: {rel.as_posix()}")
                continue
            if new_path.exists():
                preview_lines.append(f"  跳过（目标已存在）: {rel.as_posix()} → {new_name}")
                continue
            preview_lines.append(f"  {rel.as_posix()} → {new_name}")
            if not dry_run:
                try:
                    f.rename(new_path)
                    exec_lines.append(f"  ✅ {rel.as_posix()} → {new_name}")
                except OSError as e:
                    errors.append(f"{rel.as_posix()}: {e}")

        elif action in ("move", "copy"):
            dst = dest_dir / f.name
            if dst.exists():
                preview_lines.append(f"  跳过（目标已存在）: {rel.as_posix()} → {dst.relative_to(_PROJECT_ROOT).as_posix()}")
                continue
            preview_lines.append(f"  {rel.as_posix()} → {dst.relative_to(_PROJECT_ROOT).as_posix()}")
            if not dry_run:
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if action == "move":
                        f.rename(dst)
                    else:
                        shutil.copy2(f, dst)
                    exec_lines.append(f"  ✅ {rel.as_posix()} → {dst.relative_to(_PROJECT_ROOT).as_posix()}")
                except OSError as e:
                    errors.append(f"{rel.as_posix()}: {e}")

        elif action == "delete":
            preview_lines.append(f"  删除: {rel.as_posix()}")
            if not dry_run:
                try:
                    f.unlink()
                    exec_lines.append(f"  ✅ 已删除: {rel.as_posix()}")
                except OSError as e:
                    errors.append(f"{rel.as_posix()}: {e}")

        elif action == "replace":
            try:
                with open(f, "rb") as bf:
                    head = bf.read(2048)
                if b"\x00" in head:
                    preview_lines.append(f"  跳过（二进制）: {rel.as_posix()}")
                    continue
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                errors.append(f"{rel.as_posix()}: 读取失败 {e}")
                continue
            if replace_from not in text:
                preview_lines.append(f"  跳过（无匹配内容）: {rel.as_posix()}")
                continue
            count = text.count(replace_from)
            preview_lines.append(f"  {rel.as_posix()}（替换 {count} 处）")
            if not dry_run:
                try:
                    f.write_text(
                        text.replace(replace_from, replace_to),
                        encoding="utf-8",
                    )
                    exec_lines.append(f"  ✅ {rel.as_posix()}（替换 {count} 处）")
                except Exception as e:
                    errors.append(f"{rel.as_posix()}: {e}")

    if dry_run:
        preview_lines.append("\n（dry_run 预览，未实际执行。确认后请以 dry_run=False 重试）")
        body = "\n".join(preview_lines)
    else:
        body = "\n".join(exec_lines)

    if errors:
        body += f"\n\n⚠️ {len(errors)} 个文件操作失败:\n" + "\n".join(f"  {e}" for e in errors)
    return body
