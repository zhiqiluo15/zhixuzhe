"""联网调研技能 —— 搜索、抓取、摘要、对比

这是智序者第二个罐装技能，封装了"调研"这个高频通用任务的最佳实践流程：
web_search 获取结果列表 → web_fetch 抓取关键页面 → 综合产出结构化报告。
跳过 LLM 即兴规划阶段，保证调研流程的完整性和报告结构一致性。
"""

from engine.skills.base import Skill


class WebResearchSkill(Skill):
    """联网搜索+多源抓取+结构化摘要"""

    name = "web_research_summarize"
    description = "联网搜索并抓取多个网页，产出结构化调研报告（含结论、事实、来源对比）"

    triggers = [
        # 中文
        "调研", "搜索一下", "查一下", "搜一下", "查资料",
        "网上怎么说", "最新信息", "网络搜索",
        "联网查找", "帮我搜", "搜搜看",
        "研究一下", "搜集资料", "查找资料",
        # 英文
        "search for", "look up", "find online",
        "research", "web search", "google",
        "bing search", "find information",
    ]

    def plan(self, goal: str) -> list[str]:
        return [
            "使用 web_search 搜索用户目标相关的关键词，获取最相关的搜索结果列表（标题、URL、摘要），根据结果判断最相关的 3-5 个来源",
            "使用 web_fetch 逐个抓取最相关的 3-5 个网页内容，优先选择官方文档、权威来源、最新内容；跳过无法访问或内容不相关的页面",
            "基于所有抓取到的内容，产出结构化调研报告，包含：①核心结论 ②关键事实与数据 ③不同来源的观点对比/共识/分歧 ④参考来源列表（附URL）；信息不足时明确标注哪些部分未能确认",
        ]
