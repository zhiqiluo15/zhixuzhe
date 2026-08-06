"""技能基类 —— 罐装任务计划，可复用、可进化

技能 = Tool（原子动作）的上层复合体，封装了预设的 Brain 推理流程。
每个技能是一个已验证过的"最佳实践计划"，被 Router 匹配后跳过 LLM 即兴规划阶段，
直接进入执行环节，节省一次 API 调用，提高可靠性和确定性。
"""

from abc import ABC, abstractmethod


class Skill(ABC):
    """技能基类

    子类只需提供 name / description / triggers 和 plan() 方法。
    默认执行由 TaskRunner 的 ReAct 流水线接管，无需重写 execute()。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """技能名称（唯一标识）"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """技能描述（用于展示和路由匹配）"""
        ...

    @property
    @abstractmethod
    def triggers(self) -> list[str]:
        """触发关键词/短语列表，Router 用于意图匹配

        支持中英文，匹配时忽略大小写。
        短语粒度建议：2-8 个字，太短容易误匹配，太长命中率低。
        """
        ...

    @abstractmethod
    def plan(self, goal: str) -> list[str]:
        """返回该技能的预定义步骤列表

        每步是一个自然语言描述，将被 TaskRunner 的 ReAct 循环逐条执行。
        步骤要有明确的可执行性，每步对应一个独立的 Tool 调用或推理单元。
        """
        ...
