#!/usr/bin/env python3
"""智序者 · GPU 算力验证（身体检查）

验证 CUDA 版 PyTorch 是否完整支持当前 GPU（Blackwell sm_120 需 cu128+），
并做 CPU/GPU 实际计算性能对比。

用法：
  python engine/tools/verify_gpu.py              # 独立运行

API：
  verify_gpu() -> str                             # 返回格式化报告，供 Tool 调用
"""

import time

import torch

from engine.log import get_logger

logger = get_logger(__name__)


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def verify_gpu() -> str:
    """验证 GPU 算力，返回格式化报告。供 Tool 调用。"""
    lines = []

    lines.append("── PyTorch 版本信息 ─────────────────────")
    lines.append(f"PyTorch 版本: {torch.__version__}")
    lines.append(f"编译时 CUDA: {torch.version.cuda}")
    lines.append(f"cuDNN 版本:  {torch.backends.cudnn.version()}")
    lines.append(f"支持架构:    {torch.cuda.get_arch_list()}")

    lines.append("\n── CUDA 可用性 ─────────────────────────")
    if not torch.cuda.is_available():
        lines.append("❌ CUDA 不可用，GPU 无法使用")
        return "\n".join(lines)
    lines.append("✅ CUDA 可用")
    lines.append(f"GPU 型号:  {torch.cuda.get_device_name(0)}")
    lines.append(f"显存总量:  {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    cap = torch.cuda.get_device_capability(0)
    lines.append(f"计算能力:  {cap[0]}.{cap[1]}")

    # 关键：实际执行 GPU 算子
    lines.append("\n── GPU 实算测试 ────────────────────────")
    try:
        x = torch.randn(4096, 4096, device="cuda")
        y = torch.randn(4096, 4096, device="cuda")
        z = x @ y
        torch.cuda.synchronize()
        lines.append("✅ GPU 矩阵乘法（4096x4096）执行成功")
        lines.append(f"   结果数值校验: {z.float().abs().mean().item():.4f}")
    except Exception as exc:
        lines.append(f"❌ GPU 算子执行失败: {exc}")
        return "\n".join(lines)

    lines.append("\n── CPU vs GPU 性能对比 ─────────────────")
    size = 3000
    a_cpu = torch.randn(size, size)
    b_cpu = torch.randn(size, size)

    t0 = time.perf_counter()
    _ = a_cpu @ b_cpu
    cpu_time = time.perf_counter() - t0

    a_gpu = a_cpu.cuda()
    b_gpu = b_cpu.cuda()
    for _ in range(3):  # 预热
        _ = a_gpu @ b_gpu
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    _ = a_gpu @ b_gpu
    torch.cuda.synchronize()
    gpu_time = time.perf_counter() - t0

    gpu_name = torch.cuda.get_device_name(0)
    lines.append(f"CPU ({torch.get_num_threads()} 线程) 矩阵乘法 {size}x{size}: {fmt_ms(cpu_time)}")
    lines.append(f"GPU ({gpu_name}) 矩阵乘法 {size}x{size}: {fmt_ms(gpu_time)}")
    speedup = cpu_time / gpu_time
    lines.append(f"加速比: {speedup:.1f}x")

    lines.append("\n── 结论 ────────────────────────────────")
    lines.append("✅ GPU 算力正常")
    lines.append("✅ 硬进化（QLoRA 微调）的软件前置条件已就绪")

    return "\n".join(lines)


def main() -> None:
    """独立运行入口"""
    print(verify_gpu())


if __name__ == "__main__":
    main()
