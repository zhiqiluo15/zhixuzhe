"""意图路由器 —— 将用户目标匹配到合适的技能

Router 是 route+skill 架构的"route"部分。
它封装了意图→技能的匹配逻辑，TaskRunner 在规划阶段首先调用 Router，
命中则跳过 LLM 即兴规划，直接使用技能的罐装计划执行。
"""

from engine.skills.registry import SkillRegistry
from engine.skills.base import Skill


class Router:
    """意图路由器

    当前实现：基于关键词的简单匹配。
    未来可扩展为 LLM 语义匹配、嵌入向量相似度匹配等。
    """

    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def route(self, intent: str) -> Skill | None:
        """将用户意图路由到匹配的技能

        Args:
            intent: 用户原始输入/目标描述

        Returns:
            匹配到的技能实例，无匹配返回 None
        """
        return self.registry.match(intent)
