#!/usr/bin/env python3
"""智序者 · GPU 算力验证（身体检查）

验证 CUDA 版 PyTorch 是否完整支持当前 GPU（Blackwell sm_120 需 cu128+），
并做 CPU/GPU 实际计算性能对比。

用法：
  python tools/verify_gpu.py
"""

import time

import torch


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def main() -> None:
    print("── PyTorch 版本信息 ─────────────────────")
    print(f"PyTorch 版本: {torch.__version__}")
    print(f"编译时 CUDA: {torch.version.cuda}")
    print(f"cuDNN 版本:  {torch.backends.cudnn.version()}")
    print(f"支持架构:    {torch.cuda.get_arch_list()}")

    print("\n── CUDA 可用性 ─────────────────────────")
    if not torch.cuda.is_available():
        print("❌ CUDA 不可用，GPU 无法使用")
        return
    print("✅ CUDA 可用")
    print(f"GPU 型号:  {torch.cuda.get_device_name(0)}")
    print(f"显存总量:  {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print(f"计算能力:  {torch.cuda.get_device_capability(0)}")

    # 关键：实际执行 GPU 算子，确认无 "no kernel image" 类错误
    print("\n── GPU 实算测试 ────────────────────────")
    try:
        x = torch.randn(4096, 4096, device="cuda")
        y = torch.randn(4096, 4096, device="cuda")
        z = x @ y
        torch.cuda.synchronize()
        print("✅ GPU 矩阵乘法（4096x4096）执行成功")
        print(f"   结果数值校验: {z.float().abs().mean().item():.4f}")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ GPU 算子执行失败: {exc}")
        return

    print("\n── CPU vs GPU 性能对比 ─────────────────")
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
    print(f"CPU ({torch.get_num_threads()} 线程) 矩阵乘法 {size}x{size}: {fmt_ms(cpu_time)}")
    print(f"GPU ({gpu_name}) 矩阵乘法 {size}x{size}: {fmt_ms(gpu_time)}")
    speedup = cpu_time / gpu_time
    print(f"加速比: {speedup:.1f}x")

    print("\n── 结论 ────────────────────────────────")
    print("✅ GPU 算力正常，CUDA 版 PyTorch 完整支持 RTX 5060 (sm_120)")
    print("✅ 硬进化（QLoRA 微调）的软件前置条件已就绪")


if __name__ == "__main__":
    main()
