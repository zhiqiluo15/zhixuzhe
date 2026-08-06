"""智序者 v1 入口：python -m engine.core"""

import sys
from pathlib import Path


def main() -> None:
    # 确保项目根在 sys.path 开头
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))

    # ── 配置与日志（最先初始化） ──
    from engine.config import config
    from engine.log import init_logging, get_logger

    init_logging(
        log_dir=config.logging.dir,
        level=config.logging.level,
        fmt=config.logging.format,
        max_bytes=config.logging.file_max_bytes,
        backup_count=config.logging.file_backup_count,
    )
    logger = get_logger(__name__)
    logger.info("智序者 v1 启动中...")

    # ── 组装 Agent ──
    from engine.factory import create_agent

    try:
        agent = create_agent(project_root)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"已注册 {agent.tool_count} 个工具: {', '.join(agent.tools.names())}")
    logger.info(f"已注册 {agent.skill_count} 个技能")
    logger.info("智序者 v1 就绪，进入交互模式")
    agent.interactive()


if __name__ == "__main__":
    main()