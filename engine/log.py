"""智序者日志模块 —— 基于 stdlib logging 的统一日志系统

所有模块通过 from engine.log import get_logger 获取 logger，
替代原始 print() 调用。

用法：
    from engine.log import get_logger
    logger = get_logger(__name__)
    logger.info("something happened")
"""

import logging
import logging.handlers
from pathlib import Path

# 项目根
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_loggers: dict[str, logging.Logger] = {}
_initialized = False


def init_logging(log_dir: str = "logs", level: str = "INFO",
                 fmt: str | None = None, max_bytes: int = 10 * 1024 * 1024,
                 backup_count: int = 5) -> None:
    """初始化日志系统（进程生命周期内仅调用一次）。

    Args:
        log_dir: 日志目录，相对于项目根
        level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        fmt: 日志格式
        max_bytes: 单文件最大字节
        backup_count: 保留历史文件数
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    if fmt is None:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    log_path = _PROJECT_ROOT / log_dir
    log_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("zhixuzhe")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 控制台 handler（INFO 级别）
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(console)

    # 文件 handler（DEBUG 级别，全量记录）
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "agent.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt))
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。

    Args:
        name: 通常传 __name__ 即可

    Returns:
        以 'zhixuzhe.' 为前缀的 logger 实例
    """
    if not name.startswith("zhixuzhe"):
        name = f"zhixuzhe.{name.removeprefix('engine.')}"
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]
