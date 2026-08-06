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

    # ── 大脑 ──
    from engine.brain.deepseek_api import DeepSeekAPIBrain

    try:
        brain = DeepSeekAPIBrain(
            model=config.model.model,
            base_url=config.model.base_url,
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # ── 手脚 ──
    from engine.tools.registry import ToolRegistry, Tool
    from engine.tools.detect_host import detect_host
    from engine.tools.verify_gpu import verify_gpu
    from engine.tools.shell import run_shell
    from engine.tools.file_io import read_file, write_file
    from engine.tools.web_fetch import web_fetch

    tools = ToolRegistry()
    tools.register(Tool(
        name="detect_host",
        description="检测宿主机信息：操作系统、CPU、内存、磁盘、Python 版本、GPU、CUDA、PyTorch",
        func=detect_host,
    ))
    tools.register(Tool(
        name="verify_gpu",
        description="验证 GPU 算力：检查 CUDA 可用性，运行矩阵乘基准测试对比 CPU vs GPU 性能",
        func=verify_gpu,
    ))
    tools.register(Tool(
        name="run_shell",
        description=(
            "在宿主机上执行 PowerShell 命令。可用于：文件读写（cat/dir/ls）、"
            "环境检测（python -m pip list）、代码执行（python script.py）等。"
        ),
        func=run_shell,
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 PowerShell 命令",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数（默认 {config.tools.shell.default_timeout}，最大 {config.tools.shell.max_timeout}）",
                },
            },
            "required": ["command"],
        },
        max_retries=config.tools.shell.max_retries,
    ))
    tools.register(Tool(
        name="read_file",
        description="读取项目内的文件内容。适合查看代码、配置、日志等文本文件。",
        func=read_file,
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "文件路径（相对项目根或绝对路径）",
                },
            },
            "required": ["filepath"],
        },
    ))
    tools.register(Tool(
        name="write_file",
        description="在项目内写入/创建文件。适合生成代码、保存结果、更新配置。",
        func=write_file,
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "文件路径（相对项目根或绝对路径）",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容",
                },
                "append": {
                    "type": "boolean",
                    "description": "True 为追加，False 为覆盖（默认）",
                },
            },
            "required": ["filepath", "content"],
        },
    ))
    tools.register(Tool(
        name="web_fetch",
        description="获取网页内容。用于查询在线文档、API 文档、技术资料等。",
        func=web_fetch,
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "网页地址",
                },
            },
            "required": ["url"],
        },
    ))

    logger.info(f"已注册 {len(tools._tools)} 个工具: {', '.join(tools._tools)}")

    # ── 技能 ──
    from engine.skills.registry import SkillRegistry
    from engine.skills.hardware_check.skill import HardwareCheckSkill

    skills = SkillRegistry()
    skills.register(HardwareCheckSkill())
    logger.info(f"已注册 {len(skills)} 个技能")

    # ── 记忆 ──
    from engine.core.recorder import Recorder
    from engine.core.history import HistoryStore
    from engine.core.memory_reader import MemoryReader
    from engine.core.memory_manager import MemoryManager

    recorder = Recorder(root=project_root)
    history_store = HistoryStore(root=project_root)
    memory_reader = MemoryReader(root=project_root)
    memory_manager = MemoryManager(memory_reader)

    # ── 组装并启动 ──
    from engine.core.loop import Agent

    confirm_tools = set(config.agent.confirm_tools)

    agent = Agent(
        brain=brain, tools=tools,
        recorder=recorder, history_store=history_store,
        skill_registry=skills,
        memory_manager=memory_manager,
        confirm_tools=confirm_tools,
    )
    logger.info("智序者 v1 就绪，进入交互模式")
    agent.interactive()


if __name__ == "__main__":
    main()
