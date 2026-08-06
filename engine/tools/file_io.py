"""文件读写工具 —— 对项目内文件的读取与写入

安全设计：
- read_file: 限制文件大小，防止读取超大文件撑爆上下文
- write_file: 仅允许在项目根目录内写入，防止越界
"""

from pathlib import Path

from engine.config import config

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_path(filepath: str) -> Path:
    """解析文件路径。相对路径相对于项目根。"""
    p = Path(filepath)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return p.resolve()


def read_file(filepath: str, max_chars: int | None = None) -> str:
    """读取项目内文件内容。

    Args:
        filepath: 文件路径（相对于项目根或绝对路径）
        max_chars: 最大读取字符数，默认使用配置值

    Returns:
        文件内容字符串
    """
    if max_chars is None:
        max_chars = config.tools.file.max_file_size

    path = _resolve_path(filepath)

    # 安全检查：必须在项目根内
    try:
        path.relative_to(_PROJECT_ROOT)
    except ValueError:
        return f"错误: 文件不在项目目录内 — {filepath}"

    if not path.exists():
        return f"错误: 文件不存在 — {filepath}"

    if path.is_dir():
        return f"错误: 路径是目录而非文件 — {filepath}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"读取文件失败: {e}"

    if len(content) > max_chars:
        content = content[:max_chars] + (
            f"\n\n[已截断，文件共 {len(content)} 字符，仅显示前 {max_chars} 字符]"
        )

    return content


def write_file(filepath: str, content: str, append: bool = False) -> str:
    """在项目内写入文件。

    Args:
        filepath: 文件路径（相对于项目根或绝对路径）
        content: 要写入的内容
        append: True 为追加，False 为覆盖

    Returns:
        操作结果
    """
    path = _resolve_path(filepath)

    # 安全检查：必须在项目根内
    try:
        path.relative_to(_PROJECT_ROOT)
    except ValueError:
        return f"错误: 不允许写入项目目录外的文件 — {filepath}"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return f"写入文件失败: {e}"

    action = "追加" if append else "写入"
    return f"已{action}: {path.relative_to(_PROJECT_ROOT)} ({len(content)} 字符)"
