"""技能注册表 —— 管理所有技能的注册与意图匹配"""

from engine.skills.base import Skill


class SkillRegistry:
    """技能注册表

    管理所有已注册技能，提供意图匹配能力。
    匹配策略：简单关键词子串匹配（忽略大小写），命中即返回第一个匹配技能。
    """

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """注册一个技能"""
        self._skills[skill.name] = skill

    def match(self, intent: str) -> Skill | None:
        """根据用户意图匹配技能

        遍历所有技能的 triggers，对 intent 做不区分大小写的子串匹配。
        返回第一个命中的技能，无匹配返回 None。

        匹配规则：
        - 用户输入中的任意位置包含 trigger 短语即视为命中
        - 多个技能同时命中时返回第一个注册的
        - 空 intent 不进行匹配
        """
        if not intent or not intent.strip():
            return None

        intent_lower = intent.lower()
        for skill in self._skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in intent_lower:
                    return skill
        return None

    def list_descriptions(self) -> str:
        """列出所有已注册技能的摘要信息"""
        if not self._skills:
            return "（暂无已注册技能）"
        lines = []
        for skill in self._skills.values():
            triggers = ", ".join(skill.triggers[:3])
            if len(skill.triggers) > 3:
                triggers += f" ...（共 {len(skill.triggers)} 个）"
            lines.append(f"  [{skill.name}] {skill.description}")
            lines.append(f"    触发词: {triggers}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills
