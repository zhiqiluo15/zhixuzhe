"""技能链编排器 —— 顺序执行多个技能

SkillChain 是 Orchestrator 的 v1 实现（Anthropic 五模式中的 Prompt Chaining）。
它将多个技能的输出串联起来：Skill A 的结果 → 作为 Goal 喂给 Skill B。

设计原则：
- 不引入 DAG 引擎、不引入并行调度、不引入事件总线
- 只做一件事：顺序串联
- 未来的 Parallel/Evaluator 模式可以继续加在这个文件里
"""

from engine.brain.base import Brain
from engine.tools.registry import ToolRegistry
from engine.core.recorder import Recorder
from engine.core.task import TaskRunner
from engine.core.react import ConfirmCallback
from engine.core.memory_manager import MemoryManager
from engine.skills.registry import SkillRegistry
from engine.skills.base import Skill
from engine.log import get_logger

logger = get_logger(__name__)


class SkillChain:
    """顺序技能链 —— 将多个技能按顺序串联执行。

    Skill A 的输出 → 作为 Skill B 的输入 Goal → Skill B 输出 → Skill C ...

    用法：
        chain = SkillChain(brain, tools, recorder, skill_registry)
        result = chain.run("硬件检测", ["hardware_check", "report_generator"])
    """

    def __init__(
        self,
        brain: Brain,
        tools: ToolRegistry,
        recorder: Recorder,
        skill_registry: SkillRegistry,
        memory_manager: MemoryManager | None = None,
    ):
        self.task_runner = TaskRunner(
            brain, tools, recorder, skill_registry, memory_manager,
        )
        self.skill_registry = skill_registry

    def run(
        self,
        initial_goal: str,
        skill_names: list[str],
        verbose: bool = True,
        confirm_callback: ConfirmCallback | None = None,
    ) -> str:
        """按顺序执行技能链。

        Args:
            initial_goal: 初始目标
            skill_names: 技能名称列表（按注册时的 skill.name）
            verbose: 是否打印进度
            confirm_callback: HITL 确认回调

        Returns:
            最后一个技能的综合结论
        """
        if not skill_names:
            return "错误: 技能链为空，至少需要一个技能"

        current_goal = initial_goal
        chain_results: list[dict] = []

        for i, name in enumerate(skill_names):
            skill = self._find_skill(name)
            if skill is None:
                logger.error(f"技能 '{name}' 未注册，链条中断")
                return f"错误: 技能 '{name}' 未在 SkillRegistry 中注册"

            if verbose:
                print(f"\n🔗 [{i + 1}/{len(skill_names)}] {skill.name}: {skill.description}")

            # 强制走 skill 规划（不走 LLM 即兴规划兜底）
            logger.info(f"SkillChain 执行: {skill.name}（目标: {current_goal[:50]}...）")

            # 直接用 skill.plan() 生成步骤
            plan = skill.plan(current_goal)
            if verbose:
                print(f"  共 {len(plan)} 步")

            # 执行步骤
            step_results: list[str] = []
            memory_context = ""
            if self.task_runner.memory_manager:
                memory_context = self.task_runner.memory_manager.build_context(current_goal)

            for si, step in enumerate(plan):
                if verbose:
                    print(f"  ⏳ [{si + 1}/{len(plan)}] {step[:50]}...", end=" ", flush=True)
                try:
                    result = self.task_runner._execute_step(
                        current_goal, step, si, plan,
                        step_results[:si],
                        confirm_callback,
                        memory_context if si == 0 else "",
                    )
                    step_results.append(result)
                    if verbose:
                        print("✅")
                except Exception as e:
                    logger.error(f"步骤 {si + 1} 失败: {e}")
                    step_results.append(f"执行失败: {e}")
                    if verbose:
                        print(f"❌ {e}")

            # 综合
            final = self.task_runner._synthesize(current_goal, plan, step_results)

            # 记录
            self.task_runner.recorder.record_task(
                current_goal, plan, step_results, final,
                f"chain:{skill.name}",
            )

            chain_results.append({
                "skill": skill.name,
                "goal": current_goal,
                "steps": len(plan),
                "result": final,
            })

            # 下一轮的 Goal = 本轮的最终结果摘要
            current_goal = final

        if verbose:
            print(f"\n✅ 技能链执行完毕: {' → '.join(skill_names)}")

        return current_goal

    def _find_skill(self, name: str) -> Skill | None:
        """根据名称查找技能实例"""
        for skill in self.skill_registry._skills:
            if skill.name == name:
                return skill
        return None
