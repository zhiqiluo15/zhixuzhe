"""智序者入口：python -m engine.core"""

import io
import sys
from pathlib import Path

# 工具函数 stdout 捕获包装
def _capture_stdout(func):

    def wrapper(**kwargs):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            func(**kwargs)
        finally:
            sys.stdout = old
        return buf.getvalue()

    return wrapper


def main() -> None:
    # 确保项目根在 sys.path 开头
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))

    from engine.brain.deepseek_api import DeepSeekAPIBrain
    from engine.tools.registry import ToolRegistry, Tool
    from engine.tools.shell import run_shell
    from engine.skills.registry import SkillRegistry
    from engine.skills.hardware_check.skill import HardwareCheckSkill
    from engine.core.loop import Agent, DEFAULT_CONFIRM_TOOLS
    from engine.core.recorder import Recorder
    from engine.core.history import HistoryStore
    from engine.core.memory_reader import MemoryReader
    from engine.core.memory_manager import MemoryManager

    # ── 大脑 ──
    try:
        brain = DeepSeekAPIBrain()
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    # ── 手脚 ──
    from engine.tools.detect_host import main as detect_host_main
    from engine.tools.verify_gpu import main as verify_gpu_main

    tools = ToolRegistry()
    tools.register(Tool(
        name="detect_host",
        description="检测宿主机信息：操作系统、CPU、内存、磁盘、Python 版本、GPU、CUDA、PyTorch",
        func=_capture_stdout(detect_host_main),
    ))
    tools.register(Tool(
        name="verify_gpu",
        description="验证 GPU 算力：检查 CUDA 可用性，运行矩阵乘基准测试对比 CPU vs GPU 性能",
        func=_capture_stdout(verify_gpu_main),
    ))
    # Shell 命令执行（带重试 + HITL 确认保护）
    tools.register(Tool(
        name="run_shell",
        description=(
            "在宿主机上执行 PowerShell 命令。可用于：文件读写（cat/dir/ls）、"
            "环境检测（python -m pip list）、代码执行（python script.py）等。"
            "注意：命令在项目根目录下执行，超时 30 秒，非交互模式。"
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
                    "description": "超时秒数（默认 30，最大 120）",
                },
            },
            "required": ["command"],
        },
        max_retries=2,  # 网络/瞬态错误自动重试（1s, 2s 退避）
    ))

    # ── 技能 ──
    skills = SkillRegistry()
    skills.register(HardwareCheckSkill())

    # ── 记忆 ──
    recorder = Recorder(root=project_root)
    history_store = HistoryStore(root=project_root)

    # 分层记忆（读写闭合）
    memory_reader = MemoryReader(root=project_root)
    memory_manager = MemoryManager(memory_reader)

    # ── 组装并启动 ──
    agent = Agent(
        brain=brain, tools=tools,
        recorder=recorder, history_store=history_store,
        skill_registry=skills,
        memory_manager=memory_manager,
        confirm_tools=DEFAULT_CONFIRM_TOOLS,
    )
    agent.interactive()


if __name__ == "__main__":
    main()
