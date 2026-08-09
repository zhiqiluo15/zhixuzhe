"""Agent 工厂 —— 统一组装智序者 Agent 的所有组件

两个入口（CLI 和 Web Server）共享此工厂，避免组装逻辑重复。
"""

from pathlib import Path

from engine.config import config
from engine.core.loop import Agent


def create_agent(project_root: Path) -> Agent:
    """创建并返回一个完全组装的 Agent 实例。

    包括：大脑、11 个工具、5 个技能、记忆组件（Recorder / HistoryStore / MemoryManager）、
    知识学习组件（TaxonomyManager / ProfileManager）。

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

    def _make_video(text: str = "", voice: str = "zh-CN-XiaoxiaoNeural") -> str:
        """懒导入 video_maker（依赖 edge-tts/moviepy/Pillow，避免拖慢 Agent 启动）"""
        from engine.tools.video_maker import make_douyin_video
        return make_douyin_video(text=text, voice=voice)

    from engine.tools.shell import run_shell
    from engine.tools.file_io import read_file, write_file
    from engine.tools.web_fetch import web_fetch
    from engine.tools.web_search import web_search
    from engine.tools.search_file import search_file
    from engine.tools.read_data import read_data
    from engine.tools.file_manage import list_files, batch_files

    tools = ToolRegistry()
    tools.register(Tool(
        name="make_video",
        description=(
            "制作抖音竖屏短视频：将口播文案切句，用 edge-tts 合成中文配音，"
            "渲染渐变字幕背景并合成 MP4（1080x1920）。"
            "参数 text 为口播文案（留空用内置智序者宣传文案），voice 为音色。"
        ),
        func=_make_video,
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "口播文案，留空则用内置智序者宣传文案",
                },
                "voice": {
                    "type": "string",
                    "description": "edge-tts 音色，如 zh-CN-XiaoxiaoNeural（默认）/zh-CN-YunxiNeural",
                },
            },
        },
    ))
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
    tools.register(Tool(
        name="search_file",
        description="在项目代码库中按正则表达式搜索文件内容，返回 文件:行号:匹配行。用于定位代码位置、查找函数/类/关键实现。",
        func=search_file,
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "要搜索的正则表达式（忽略大小写），如 'def add' 或 'Cache\\\\.class'",
                },
                "path": {
                    "type": "string",
                    "description": "搜索起始目录（相对项目根，默认 '.' 整个项目）",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件名过滤 glob，如 '*.py'（默认全部文本文件）",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回匹配条数（默认 50，上限 200）",
                },
            },
            "required": ["pattern"],
        },
    ))
    tools.register(Tool(
        name="read_data",
        description="读取 CSV/JSON/JSONL 数据文件，输出结构预览与统计摘要（列、类型、数值列 count/min/max/mean/std、类别列唯一值与 top、前几行）。数据分析第一步。",
        func=read_data,
        parameters={
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "数据文件路径（相对项目根或绝对路径）",
                },
                "format": {
                    "type": "string",
                    "description": "数据格式：auto（按扩展名推断）/csv/json/jsonl/text",
                },
                "preview_rows": {
                    "type": "integer",
                    "description": "预览行数（默认 10，上限 50）",
                },
            },
            "required": ["filepath"],
        },
    ))
    tools.register(Tool(
        name="list_files",
        description="列出目录/glob 匹配的文件清单（名称+大小+修改时间）。只读，用于了解项目文件结构。",
        func=list_files,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "起始目录（相对项目根，默认 '.'）",
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名 glob 过滤，如 '*.log'",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归子目录（默认 False）",
                },
            },
        },
    ))
    tools.register(Tool(
        name="batch_files",
        description="批量文件操作：rename/move/copy/delete/replace。默认 dry_run 预览不执行，确认后传 dry_run=False 实际执行。危险操作需先预览。",
        func=batch_files,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作：rename（文件名文本替换）/move/copy/delete/replace（内容替换）",
                },
                "pattern": {
                    "type": "string",
                    "description": "匹配文件的 glob（相对项目根），如 '*.tmp'、'logs/*.log'",
                },
                "target": {
                    "type": "string",
                    "description": "move/copy 的目标目录（相对项目根）",
                },
                "replace_from": {
                    "type": "string",
                    "description": "rename 的文件名替换文本 / replace 的内容查找文本",
                },
                "replace_to": {
                    "type": "string",
                    "description": "替换后的文本",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "True 预览不执行（默认），False 实际执行",
                },
            },
            "required": ["action", "pattern"],
        },
    ))

    # ── 技能 ──
    from engine.skills.registry import SkillRegistry
    from engine.skills.hardware_check.skill import HardwareCheckSkill
    from engine.skills.web_research.skill import WebResearchSkill
    from engine.skills.code_explore.skill import CodeSearchSkill
    from engine.skills.data_analysis.skill import DataAnalysisSkill
    from engine.skills.file_manage.skill import FileManageSkill

    skills = SkillRegistry()
    # 注册顺序影响 Router 首匹配：含显式动作词（搜索/查/调研）的 web 技能优先，
    # 代码领域词（代码/源码）次之，数据领域词（数据/表格）再次，文件领域词（文件/批量）再次，领域名词技能（硬件）最后
    skills.register(WebResearchSkill())
    skills.register(CodeSearchSkill())
    skills.register(DataAnalysisSkill())
    skills.register(FileManageSkill())
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

    # ── 知识学习 ──
    from engine.core.taxonomy import TaxonomyManager
    from engine.core.profile import ProfileManager

    taxonomy = TaxonomyManager(root=project_root)
    taxonomy.load()
    profile_manager = ProfileManager(root=project_root)

    # ── 组装 ──
    confirm_tools = set(config.agent.confirm_tools)

    return Agent(
        brain=brain, tools=tools,
        recorder=recorder, history_store=history_store,
        skill_registry=skills,
        memory_manager=memory_manager,
        confirm_tools=confirm_tools,
        taxonomy=taxonomy,
        profile_manager=profile_manager,
    )