"""测试夹具 —— 为所有测试提供共享的 setup"""

import sys
import tempfile
from pathlib import Path

import pytest

# 确保项目根在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.core.recorder import Recorder


@pytest.fixture
def root() -> Path:
    """创建带测试数据的临时项目根目录"""
    with tempfile.TemporaryDirectory() as tmp:
        root_path = Path(tmp)

        # 创建 memory 目录结构
        (root_path / "memory" / "diary").mkdir(parents=True, exist_ok=True)
        (root_path / "memory" / "experience").mkdir(parents=True, exist_ok=True)

        recorder = Recorder(root=root_path)

        # 模拟几次真实交互的日记
        recorder.record(
            "帮我检测这台电脑的硬件",
            "已检测：CPU Intel 14代，GPU RTX 5060 8GB，内存 16GB。",
        )
        recorder.record(
            "QLoRA 微调需要什么条件？",
            "QLoRA 需要至少 8GB 显存，你的 RTX 5060 刚好满足。推荐 4-bit 量化。",
        )
        recorder.record(
            "今天天气怎么样？",
            "抱歉，我还没有接入天气 API，无法查询。",
        )
        recorder.record(
            "什么是 Python 装饰器？",
            "装饰器是一种修改函数行为的语法糖…",
        )

        # 记录一次任务
        recorder.record_task(
            goal="全面检测硬件并判断 QLoRA 微调条件",
            plan=["检测硬件", "验证 GPU 算力", "综合评估"],
            step_results=[
                "CPU: Intel 14代, GPU: RTX 5060 8GB",
                "矩阵乘加速 13.4x，CUDA 可用",
                "8GB 显存满足 QLoRA 最低要求，推荐 3B-4B 模型",
            ],
            final_answer="你的 RTX 5060 8GB 刚好进入 QLoRA 舒适区，推荐从 Qwen2.5-3B 开始。",
            plan_source="skill:hardware_check",
        )

        # 写一条经验
        recorder.record_experience(
            scene="在 RTX 5060 上尝试 QLoRA 微调 7B 模型时遇到 OOM",
            lesson="必须开启 gradient checkpointing 并将 batch size 设为 1",
        )

        yield root_path
