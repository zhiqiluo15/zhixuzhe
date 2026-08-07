"""技能库 —— 基因层，可开源

技能是 Tool（原子动作）的上层复合体，封装了预设的 Brain 推理流程。
每个技能目录一个子目录，内含 skill.py + 可选脚本 + README。

当前结构：
- base.py / registry.py: 技能基础设施
- hardware_check/: 硬件检测 + QLoRA 可行性判断
- web_research/: 联网搜索 + 多源抓取 + 结构化调研
- code_explore/: 项目代码库搜索 + 精读 + 结构化代码调研
- data_analysis/: 数据文件读取 + 统计洞察 + 结构化分析报告
"""
from engine.skills.base import Skill
from engine.skills.registry import SkillRegistry
