#!/usr/bin/env python3
"""智序者 · 宿主机检测（身体感知）

功能：
  1. 全面检测宿主机硬件与软件情况（OS/CPU/内存/磁盘/Python/GPU/CUDA/PyTorch）
  2. 生成版本化身体档案到 memory/body/，并同步 latest.md
  3. 与上一版档案对比，识别宿主机是否变更（换机检测）

用法：
  python engine/tools/detect_host.py            # 独立运行，打印摘要

API：
  detect_host() -> str                          # 返回格式化报告，供 Tool 调用
"""

import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from engine.log import get_logger

logger = get_logger(__name__)

# 项目根 = engine/tools/ 向上三级
ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE_DIR = ROOT / "memory" / "body"
LATEST_FILE = PROFILE_DIR / "latest.md"

# 用于宿主机变更对比的核心身份字段
IDENTITY_KEYS = ["主机名", "操作系统", "CPU 型号", "物理核心数", "GPU 型号"]


def _run(cmd: list[str], timeout: int = 15) -> str | None:
    """运行命令并返回 stdout，失败或超时返回 None。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def detect_os() -> dict:
    return {
        "主机名": socket.gethostname(),
        "操作系统": platform.system(),
        "系统版本": platform.release(),
        "系统完整信息": platform.platform(),
        "架构": platform.machine(),
    }


def detect_cpu() -> dict:
    import psutil

    cpu_freq = psutil.cpu_freq()
    freq_str = f"{cpu_freq.current:.0f} MHz" if cpu_freq and cpu_freq.current else "未知"
    info = {
        "CPU 型号": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "未知"),
        "物理核心数": psutil.cpu_count(logical=False) or "未知",
        "逻辑线程数": psutil.cpu_count(logical=True) or "未知",
        "当前频率": freq_str,
    }
    return info


def detect_memory() -> dict:
    import psutil

    mem = psutil.virtual_memory()
    gb = 1024**3
    return {
        "内存总量": f"{mem.total / gb:.1f} GB",
        "内存可用": f"{mem.available / gb:.1f} GB",
        "内存使用率": f"{mem.percent}%",
    }


def detect_disk() -> dict:
    import psutil

    gb = 1024**3
    lines = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            lines.append(
                f"- {part.device} ({part.mountpoint}) 总 {usage.total / gb:.0f} GB / "
                f"可用 {usage.free / gb:.0f} GB"
            )
        except (PermissionError, OSError):
            continue
    return {"磁盘分区": "\n".join(lines) if lines else "无法读取"}


def detect_python() -> dict:
    return {
        "Python 版本": platform.python_version(),
        "Python 路径": sys.executable,
        "pip": shutil.which("pip") or "未找到",
    }


def detect_gpu() -> dict:
    """通过 nvidia-smi 检测 NVIDIA GPU，无 NVIDIA 卡时报告无。"""
    if os.name == "nt":
        nvidia_smi = r"C:\Windows\System32\nvidia-smi.exe"
    else:
        nvidia_smi = shutil.which("nvidia-smi")

    if not nvidia_smi or not os.path.exists(nvidia_smi):
        return {"GPU 型号": "无 NVIDIA GPU（未检测到 nvidia-smi）"}

    query = _run([nvidia_smi, "--query-gpu=name,memory.total,driver_version",
                  "--format=csv,noheader"])
    if not query:
        return {"GPU 型号": "nvidia-smi 存在但查询失败"}

    lines = []
    for line in query.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            lines.append(f"- {parts[0]}（显存 {parts[1]}，驱动 {parts[2]}）")
        else:
            lines.append(f"- {line}")

    # CUDA 版本（nvidia-smi 顶部信息）
    cuda_ver = _run([nvidia_smi, "--query-gpu=compute_cap", "--format=csv,noheader"])
    return {"GPU 列表": "\n".join(lines), "CUDA 支持": cuda_ver if cuda_ver else "未知"}


def detect_cuda() -> dict:
    """检测 nvcc（CUDA 工具链）是否可用。"""
    nvcc = shutil.which("nvcc")
    if not nvcc:
        return {"CUDA 工具链(nvcc)": "未安装或不在 PATH"}
    output = _run([nvcc, "--version"])
    if output:
        for line in output.splitlines():
            if "release" in line.lower():
                return {"CUDA 工具链(nvcc)": line.strip()}
    return {"CUDA 工具链(nvcc)": "已安装（版本读取失败）"}


def detect_torch() -> dict:
    """检测 PyTorch 是否可用及其 CUDA 支持（硬进化的关键判据）。"""
    try:
        import torch
    except ImportError:
        return {"PyTorch": "未安装", "PyTorch CUDA 可用": "否"}
    cuda_ok = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if cuda_ok else "无"
    return {
        "PyTorch": torch.__version__,
        "PyTorch CUDA 可用": "是" if cuda_ok else "否",
        "PyTorch 识别 GPU": gpu_name,
    }


def read_latest() -> dict | None:
    """读取上一版 latest.md 的身份字段，用于变更对比。"""
    if not LATEST_FILE.exists():
        return None
    content = LATEST_FILE.read_text(encoding="utf-8", errors="ignore")
    previous = {}
    for key in IDENTITY_KEYS:
        for line in content.splitlines():
            if line.startswith(f"- {key}："):
                previous[key] = line.split("：", 1)[1].strip()
                break
    return previous or None


def detect_host() -> str:
    """检测宿主机信息，保存档案，返回格式化报告。供 Tool 调用。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    sections = {
        "系统信息": detect_os(),
        "CPU": detect_cpu(),
        "内存": detect_memory(),
        "磁盘": detect_disk(),
        "Python 环境": detect_python(),
        "GPU": detect_gpu(),
        "CUDA": detect_cuda(),
        "PyTorch": detect_torch(),
    }

    lines = [
        "# 智序者 · 宿主机身体档案",
        "",
        f"> 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 检测脚本：tools/detect_host.py",
        "",
    ]
    for title, data in sections.items():
        lines.append(f"## {title}")
        lines.append("")
        for key, value in data.items():
            lines.append(f"- {key}：{value}")
        lines.append("")

    content = "\n".join(lines)

    snapshot = PROFILE_DIR / f"{timestamp}.md"
    snapshot.write_text(content, encoding="utf-8")

    # 宿主机变更对比
    previous = read_latest()
    changed = None
    if previous:
        current = {}
        for key in IDENTITY_KEYS:
            for line in content.splitlines():
                if line.startswith(f"- {key}："):
                    current[key] = line.split("：", 1)[1].strip()
                    break
        changed_keys = [k for k in IDENTITY_KEYS if current.get(k) != previous.get(k)]
        changed = changed_keys if changed_keys else []

    LATEST_FILE.write_text(content, encoding="utf-8")

    # 日志
    logger.info(f"身体档案已生成: {snapshot.relative_to(ROOT)}")

    # 构建摘要
    summary_lines = [
        f"身体档案已生成: {snapshot.relative_to(ROOT)}",
        "",
        "── 宿主机摘要 ────────────────────────────",
    ]
    for key in ["主机名", "操作系统", "CPU 型号", "内存总量"]:
        for line in content.splitlines():
            if line.startswith(f"- {key}："):
                summary_lines.append(f"  {line[2:]}")
                break
    gpu_line = next((l for l in content.splitlines()
                     if l.startswith("- GPU 列表：") or l.startswith("- GPU 型号：")), None)
    if gpu_line:
        summary_lines.append(f"  {gpu_line[2:]}")

    if changed is None:
        summary_lines.append("\n（首次建档，无历史对比）")
    elif changed:
        summary_lines.append(f"\n⚠️  检测到宿主机变更：{', '.join(changed)}")
    else:
        summary_lines.append("\n（与上一版档案一致，未检测到宿主机变更）")

    return "\n".join(summary_lines)


def main() -> None:
    """独立运行入口"""
    print(detect_host())


if __name__ == "__main__":
    main()
