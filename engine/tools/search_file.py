"""代码搜索工具 —— 在项目内按正则表达式搜索文件内容（grep）

零依赖实现：os.walk 递归遍历 + re 正则匹配，返回 `文件:行号: 内容` 格式。
定位代码位置、查找函数/类/关键实现时使用，是 code_search_explore 技能的基础手脚。

安全与性能设计（沿用 file_io 的边界约定）：
- 路径限制在项目根目录内，越界拒绝
- 自动跳过二进制文件与常见无关目录（.git/__pycache__/依赖等）
- 单文件大小上限 + 结果条数上限，防止撑爆上下文
"""

import os
import re
from fnmatch import fnmatch
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 忽略目录：版本控制、缓存、依赖、构建产物
_IGNORE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", "node_modules",
    ".venv", "venv", "dist", "build", "target", ".cargo",
}

# 二进制扩展名黑名单（跳过，避免误读）
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".exe", ".dll", ".so",
    ".woff", ".woff2", ".ttf", ".otf", ".pyc", ".pyd", ".class",
    ".lock", ".db", ".sqlite",
}

# 单文件超过该字节数直接跳过（大文件逐行读太慢）
MAX_FILE_BYTES = 1_000_000

# 单行内容最长保留字符数
MAX_LINE_CHARS = 200


def _resolve_path(path: str) -> Path:
    """解析路径。相对路径相对于项目根。"""
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return p.resolve()


def search_file(
    pattern: str,
    path: str = ".",
    file_pattern: str = "",
    max_results: int = 50,
) -> str:
    """在项目内递归搜索文件内容。

    Args:
        pattern: 要搜索的正则表达式（忽略大小写）
        path: 搜索起始目录（相对项目根或绝对路径，默认整个项目）
        file_pattern: 文件名过滤 glob（如 "*.py"），为空则匹配所有文本文件
        max_results: 最多返回多少条匹配（默认 50，上限 200）

    Returns:
        匹配结果文本，格式：文件路径:行号: 内容
    """
    if not pattern or not pattern.strip():
        return "错误: 搜索模式不能为空"
    if not path or not path.strip():
        path = "."
    max_results = max(1, min(max_results, 200))

    root = _resolve_path(path)
    # 安全检查：必须在项目根内
    try:
        root.relative_to(_PROJECT_ROOT)
    except ValueError:
        return f"错误: 搜索路径不在项目目录内 — {path}"
    if not root.exists():
        return f"错误: 搜索路径不存在 — {path}"

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"错误: 无效的正则表达式 — {e}"

    hits: list[str] = []
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        # 剪枝：跳过无关目录
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]

        for fname in filenames:
            if file_pattern and not fnmatch(fname, file_pattern):
                continue
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in _BINARY_EXTS:
                continue
            try:
                if fpath.stat().st_size > MAX_FILE_BYTES:
                    continue
                with open(fpath, "rb") as bf:
                    head = bf.read(2048)
                if b"\x00" in head:  # 二进制检测：前 2KB 含 NUL 视为二进制
                    continue
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rel = fpath.relative_to(_PROJECT_ROOT)
            for lineno, line in enumerate(text.splitlines(), 1):
                if len(hits) >= max_results:
                    truncated = True
                    break
                if regex.search(line):
                    hits.append(f"{rel}:{lineno}: {line.strip()[:MAX_LINE_CHARS]}")
            if len(hits) >= max_results:
                truncated = True
                break
        if len(hits) >= max_results:
            truncated = True
            break

    if not hits:
        return f'未找到匹配 "{pattern}" 的代码（目录: {path}）'

    lines = [f'搜索 "{pattern}"（找到 {len(hits)} 条匹配）\n']
    lines.extend(hits)
    if truncated:
        lines.append(f"\n（已达结果上限 {max_results} 条，可缩小搜索范围或增加 max_results）")
    return "\n".join(lines)
