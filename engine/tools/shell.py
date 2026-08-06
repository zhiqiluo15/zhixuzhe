"""命令执行工具 —— 在宿主机上执行 Shell 命令（PowerShell）

安全设计：
- 超时限制（默认 30 秒，最大 120 秒）
- 工作目录限制在项目根目录
- 输出自动截断（复用 react_loop 的 MAX_TOOL_OUTPUT_CHARS）
- 非交互模式（-NoProfile），防止卡在提示符
"""

import subprocess
from pathlib import Path

from engine.config import config

# 项目根目录（工具脚本位于 engine/tools/，向上两级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run_shell(command: str, timeout: int | None = None) -> str:
    """执行 PowerShell 命令（Windows），返回 stdout + stderr + exit code

    Args:
        command: 要执行的 PowerShell 命令
        timeout: 超时秒数（默认 30，最大 120）

    Returns:
        命令输出（stdout），附加 stderr 和 exit code（如有）
    """
    if timeout is None:
        timeout = config.tools.shell.default_timeout
    timeout = min(timeout, config.tools.shell.max_timeout)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_PROJECT_ROOT),
            # 防止子进程继承 stdin，避免卡在交互输入
            stdin=subprocess.DEVNULL,
        )
        parts = []
        if result.stdout.strip():
            parts.append(result.stdout.strip())
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.strip()}")
        if result.returncode != 0:
            parts.append(f"[exit code: {result.returncode}]")
        return "\n".join(parts) if parts else "(无输出)"

    except subprocess.TimeoutExpired:
        return f"命令超时（>{timeout}秒），已终止"
    except FileNotFoundError:
        return "错误: 找不到 PowerShell，当前仅支持 Windows"
    except Exception as e:
        return f"命令执行异常: {e}"
