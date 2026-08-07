"""数据分析技能 —— 读取数据文件、统计洞察、产出分析报告

这是智序者第四个罐装技能，封装"数据分析"这一高频通用任务的最佳实践流程：
read_data 读取并获取统计摘要 → Brain 深度分析 → 产出结构化分析报告（含可视化描述）。

触发词设计遵循 Router 沉淀原则（CHANGELOG 2026-08-07）：
- 触发词一律带"数据/Data/csv/json/表格"等绑定词，保证领域特异性；
- 刻意不用"分析一下""看一下"等宽泛动作词（会与"分析一下代码"等代码语境冲突），
  避免被 code_search_explore 的意图抢占或反向抢占。
"""

from engine.skills.base import Skill


class DataAnalysisSkill(Skill):
    """数据文件读取与分析：概览 → 洞察 → 结构化报告"""

    name = "data_analysis_visual"
    description = "读取 CSV/JSON/JSONL 数据文件并分析：数据概览、统计洞察、趋势与异常、产出结构化分析报告"

    triggers = [
        # 中文 - 动作词 + 数据绑定
        "数据分析", "分析数据", "数据统计", "统计数据",
        "分析一下数据", "统计一下数据", "分析这个数据",
        "看看数据", "看数据", "分析表格", "数据文件",
        # 中文 - 领域定位
        "数据里", "数据中", "数据概况", "数据摘要",
        "这个表格", "表格数据", "csv数据", "json数据",
        "数据趋势", "数据分布",
        # 英文
        "analyze data", "analyze the data", "data analysis",
        "look at the data", "data stats", "data summary",
        "data overview", "analyze csv", "analyze json",
    ]

    def plan(self, goal: str) -> list[str]:
        return [
            "使用 read_data 读取目标数据文件（CSV/JSON/JSONL），获取数据规模、列结构与类型、数值列统计（count/min/max/mean/std）、类别列唯一值与 top 值、前几行预览",
            "基于数据摘要深入分析：识别关键模式、趋势、分布特征、异常值，以及数据质量问题（缺失值、异常格式、列类型不一致）；对关键列做对比与相关性推断",
            "产出结构化数据分析报告：①数据概览（规模/结构/质量）②关键发现（趋势/模式/异常，附具体数值佐证）③可视化描述（用 ASCII 图或文字化图表呈现关键分布）④结论与建议；信息不足时明确标注哪些部分未能确认",
        ]
