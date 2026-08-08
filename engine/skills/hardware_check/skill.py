"""硬件检测技能 —— 全面检测宿主机并判断 QLoRA 微调条件

这是智序者首个罐装技能，来自 CHANGELOG 记录的已验证任务计划。
原本每次走 TaskRunner LLM 即兴规划，现固化为此技能的预设步骤，
省去规划阶段的 API 调用，保证每次执行的一致性。
"""

from engine.skills.base import Skill


class HardwareCheckSkill(Skill):
    """全面硬件检测 + QLoRA 可行性分析"""

    name = "hardware_check"
    description = "全面检测宿主机硬件并判断 QLoRA 微调条件"

    triggers = [
        # 中文
        "硬件检测", "检查硬件", "硬件配置", "电脑配置",
        "QLoRA微调", "跑QLoRA", "QLoRA可行", "QLoRA条件",
        "微调条件", "GPU检测", "显卡配置",
        "硬件信息", "检测配置", "检查配置",
        "能微调吗", "能不能微调", "微调可行",
        "显存够不够", "显存够吗",
        "检查GPU", "GPU是否可用", "硬件诊断",
        # 英文（注意子串匹配对语序敏感，需覆盖自然表达的多种语序）
        "detect host", "check hardware", "hardware check",
        "system info", "system information",
        "gpu check", "check gpu", "verify gpu", "gpu available",
        "gpu availability", "is gpu working", "check if gpu",
        "can i run qlora", "hardware diagnostics",
        "check my hardware", "hardware info",
    ]

    def plan(self, goal: str) -> list[str]:
        return [
            "检测宿主机信息：操作系统、CPU、内存、磁盘、Python版本、GPU型号、CUDA版本",
            "验证GPU算力：检查CUDA可用性，运行矩阵乘基准测试，对比CPU vs GPU性能",
            "综合分析：基于检测结果判断QLoRA微调可行性，给出分层结论（舒适区配置/极限区配置/不可行配置）及具体模型推荐",
        ]
