"""Agent 工厂 —— 统一组装智序者 Agent 的所有组件

两个入口（CLI 和 Web Server）共享此工厂，避免组装逻辑重复。
"""

from pathlib import Path

from engine.config import config
from engine.core.loop import Agent


def create_agent(project_root: Path) -> Agent:
    """创建并返回一个完全组装的 Agent 实例。

    包括：大脑、6 个工具、技能注册表、记忆组件（Recorder / HistoryStore / MemoryManager）。

    Args:
        project_root: 项目根目录路径

    Returns:
        组装完毕的 Agent 实例

    Raises:
        ValueError: 如果 API Key 未配置
    """
    # ── 大脑 ──
    from engine.brain.deepseek_api import DeepSeekAPIBrain

    brain = DeepSeekAPIBrain(
        model=config.model.model,
        base_url=config.model.base_url,
    )

    # ── 手脚 ──
    from engine.tools.registry import ToolRegistry, Tool
    from engine.tools.detect_host import detect_host
    from engine.tools.verify_gpu import verify_gpu
    from engine.tools.shell import run_shell
    from engine.tools.file_io import read_file, write_file
    from engine.tools.web_fetch import web_fetch
    from engine.tools.web_search import web_search

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
    tools.register(Tool(
        name="web_search",
        description="搜索网页，返回标题+URL+摘要的结果列表。用于查找在线资料、官方文档、技术方案等不知道具体URL时。",
        func=web_search,
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回几条结果（默认 8，上限 20）",
                },
            },
            "required": ["query"],
        },
    ))

    # ── 技能 ──
    from engine.skills.registry import SkillRegistry
    from engine.skills.hardware_check.skill import HardwareCheckSkill
    from engine.skills.web_research.skill import WebResearchSkill

    skills = SkillRegistry()
    # 注册顺序影响 Router 首匹配：含显式动作词（搜索/查/调研）的技能优先，
    # 领域名词技能（硬件/代码/数据）在后，避免"搜索 QLoRA 论文"误匹配硬件检测
    skills.register(WebResearchSkill())
    skills.register(HardwareCheckSkill())

    # ── 记忆 ──
    from engine.core.recorder import Recorder
    from engine.core.history import HistoryStore
    from engine.core.memory_reader import MemoryReader
    from engine.core.memory_manager import MemoryManager

    recorder = Recorder(root=project_root)
    history_store = HistoryStore(root=project_root)
    memory_reader = MemoryReader(root=project_root)
    memory_manager = MemoryManager(memory_reader)

    # ── 组装 ──
    confirm_tools = set(config.agent.confirm_tools)

    return Agent(
        brain=brain, tools=tools,
        recorder=recorder, history_store=history_store,
        skill_registry=skills,
        memory_manager=memory_manager,
        confirm_tools=confirm_tools,
    )