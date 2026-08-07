"""自主任务环路 —— 目标驱动的多步执行

流程：规划 → 逐步执行（每步可调工具） → 综合结论 → 记录

区别于普通对话：
- 普通模式: 一问一答 + 可选工具调用
- 任务模式: 用户给目标，智序者自主分解为步骤，逐步执行后给出综合结论
"""

import json
import re

from typing import Callable

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry
from engine.skills.registry import SkillRegistry
from engine.core.router import Router
from engine.core.recorder import Recorder
from engine.core.memory_manager import MemoryManager
from engine.core.react import react_loop, ConfirmCallback
from engine.config import config
from engine.log import get_logger

logger = get_logger(__name__)

# 规划提示词
PLAN_SYSTEM = """你是一个任务规划器。将用户目标分解为具体、可执行的步骤。

可用工具：{tools}

输出纯 JSON（不要 markdown 包裹，不要额外文字）：
{{"steps": ["步骤1描述", "步骤2描述"]}}

规则：
- 每步是一个独立可完成的操作
- 优先使用可用工具获取真实信息
- 不超过 5 步
- 简单目标 1-2 步即可"""

# 执行提示词
EXECUTE_SYSTEM = """执行以下任务步骤。用工具获取真实信息，不要编造。

目标：{goal}
当前步骤：{step}{context}{memory}

完成后用简洁语言汇报结果。"""

# 综合提示词
SYNTHESIZE_SYSTEM = """基于以下执行结果，回答用户的原始目标。

目标：{goal}

各步骤执行结果：
{results}

请给出综合性的最终回答，要具体、有信息量、不编造。"""

# 经验反思提示词（自进化闭环的"经验沉淀"环节）
REFLECT_SYSTEM = """基于以下任务执行过程，提炼一条可复用的经验。

任务目标：{goal}
最终结论：{final}

只在本次执行有值得记住的教训（踩过的坑、有效的方法、特殊情况、边界条件）时，
输出纯 JSON：
{{"scene": "场景描述（发生了什么，要具体）", "lesson": "教训（一句话可复用结论）"}}

如果没有值得沉淀的内容（普通顺利执行、常识性结论），输出：
{{"skip": true}}

规则：
- 经验要有稀缺性，常识性内容一律 skip
- scene 要具体到能复现判断，lesson 要能直接指导下次决策
- 不确定就 skip，宁缺毋滥"""


class TaskRunner:
    """自主任务执行器 —— 规划 → 执行 → 综合 → 记录"""

    def __init__(
        self,
        brain: Brain,
        tools: ToolRegistry,
        recorder: Recorder,
        skill_registry: SkillRegistry | None = None,
        memory_manager: MemoryManager | None = None,
    ):
        self.brain = brain
        self.tools = tools
        self.recorder = recorder
        self.router = Router(skill_registry) if skill_registry else None
        self.memory_manager = memory_manager

    def run(
        self,
        goal: str,
        verbose: bool = True,
        confirm_callback: ConfirmCallback | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> str:
        """执行一个目标，返回最终结论"""

        def _vprint(msg: str) -> None:
            if verbose:
                if verbose_callback is not None:
                    verbose_callback(msg)
                else:
                    print(msg)

        # 1. 规划（优先技能匹配 → 回退 LLM 即兴规划）
        plan_source = "llm"
        skill = self.router.route(goal) if self.router else None

        if skill:
            logger.info(f"匹配技能: {skill.name}")
            _vprint(f"🎯 匹配技能: {skill.name}（{skill.description}）")
            plan = skill.plan(goal)
            plan_source = f"skill:{skill.name}"
        else:
            logger.info("LLM 即兴规划中...")
            _vprint("📋 规划中...")
            plan = self._plan(goal)

        _vprint(f"共 {len(plan)} 步")
        for i, s in enumerate(plan):
            _vprint(f"  [{i + 1}] {s}")

        # 2. 注入记忆上下文
        memory_context = ""
        if self.memory_manager:
            memory_context = self.memory_manager.build_context(goal)

        # 3. 执行 + 综合（复用公共 execute_plan，与 SkillChain 同源）
        verbose_cb = (lambda m: _vprint(m)) if verbose else None
        final, step_results = self.execute_plan(
            goal, plan, confirm_callback, verbose_cb, memory_context,
        )
        _vprint("完成")

        # 4. 记录
        self.recorder.record_task(goal, plan, step_results, final, plan_source)

        # 5. 反思：沉淀经验（自进化闭环的"经验"环节）
        self._reflect_experience(goal, final)

        return final

    def execute_plan(
        self,
        goal: str,
        plan: list[str],
        confirm_callback: ConfirmCallback | None = None,
        verbose_callback: Callable[[str], None] | None = None,
        memory_context: str = "",
    ) -> tuple[str, list[str]]:
        """执行一个已确定的计划，返回 (综合结论, 各步结果列表)。

        公共方法，供 SkillChain 等编排器复用，避免访问私有 _execute_step / _synthesize。
        TaskRunner.run 内部也调此方法，保证单技能与链式执行行为一致。
        """
        step_results: list[str] = []
        for i, step in enumerate(plan):
            if verbose_callback:
                verbose_callback(f"\n⏳ [{i + 1}/{len(plan)}] {step[:50]}...")
            try:
                result = self._execute_step(
                    goal, step, i, plan, step_results[:i],
                    confirm_callback,
                    memory_context if i == 0 else "",
                )
                step_results.append(result)
                if verbose_callback:
                    verbose_callback("✅")
            except Exception as e:
                logger.error(f"步骤 {i + 1} 执行失败: {e}")
                step_results.append(f"执行失败: {e}")
                if verbose_callback:
                    verbose_callback(f"❌ {e}")

        if verbose_callback:
            verbose_callback("\n📝 综合分析中...")
        final = self._synthesize(goal, plan, step_results)
        return final, step_results

    def _reflect_experience(self, goal: str, final: str) -> None:
        """任务完成后反思，让 Brain 提炼可复用经验写入 experience。

        经验沉淀是自进化闭环的关键环节。Brain 判断本次执行是否有值得记住的
        教训，有则输出 JSON 由 Recorder 写入经验库；无则 skip，避免经验库膨胀。
        反思失败不阻断主流程。
        """
        messages = [
            Message(
                role="system",
                content=REFLECT_SYSTEM.format(goal=goal, final=final[:500]),
            ),
            Message(role="user", content="请反思并提炼经验。"),
        ]
        try:
            response = self.brain.think(messages)
            text = response.content.strip()
            # 兼容 markdown 代码块包裹
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            data = json.loads(text)
            if data.get("skip"):
                logger.debug("经验反思：本次无值得沉淀的内容")
                return
            scene = str(data.get("scene", "")).strip()
            lesson = str(data.get("lesson", "")).strip()
            if scene and lesson:
                self.recorder.record_experience(scene, lesson)
                logger.info(f"已沉淀经验: {scene[:50]}...")
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"经验反思未产出有效 JSON，跳过: {e}")
        except Exception as e:
            logger.debug(f"经验反思失败（不阻断主流程）: {e}")

    # ── 内部方法 ──

    def _plan(self, goal: str) -> list[str]:
        """用大脑分解目标为步骤列表"""
        tool_names = ", ".join(self.tools.names()) if self.tools else "无"
        system = PLAN_SYSTEM.format(tools=tool_names)

        messages = [
            Message(role="system", content=system),
            Message(role="user", content=goal),
        ]

        for attempt in range(config.task.plan_retries):
            response = self.brain.think(messages)
            steps = self._extract_json_steps(response.content)
            if steps:
                return steps[:config.task.max_steps]
            logger.debug(f"规划解析失败，重试 {attempt + 1}/{config.task.plan_retries}")
            messages.append(response)
            messages.append(Message(
                role="user",
                content="请只输出纯JSON，不要用markdown代码块包裹。格式：{\"steps\": [\"步骤1\", \"步骤2\"]}",
            ))

        # 兜底：整个目标作为单步
        logger.warning("规划解析全部失败，使用兜底单步")
        return [goal]

    def _execute_step(
        self,
        goal: str,
        step: str,
        step_idx: int,
        plan: list[str],
        previous: list[str],
        confirm_callback: ConfirmCallback | None = None,
        memory_context: str = "",
    ) -> str:
        """执行单个步骤（带工具调用的 ReAct 循环）"""
        context = ""
        if previous:
            prev_text = "\n".join(
                f"  步骤{j + 1}: {plan[j]}\n  结果: {r[:150]}"
                for j, r in enumerate(previous)
            )
            context = f"\n\n之前的步骤已完成：\n{prev_text}"

        memory = ""
        if memory_context and step_idx == 0:
            memory = f"\n\n{memory_context}"

        system = EXECUTE_SYSTEM.format(
            goal=goal, step=step, context=context, memory=memory,
        )
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=f"请执行第 {step_idx + 1}/{len(plan)} 步"),
        ]

        response = react_loop(
            self.brain, messages, self.tools,
            confirm_callback=confirm_callback,
        )

        return response.content

    def _synthesize(self, goal: str, plan: list[str], step_results: list[str]) -> str:
        """综合所有步骤结果，生成最终回答"""
        results_text = "\n\n".join(
            f"步骤 {i + 1}: {plan[i]}\n结果: {step_results[i]}"
            for i in range(len(plan))
        )
        system = SYNTHESIZE_SYSTEM.format(goal=goal, results=results_text)

        messages = [
            Message(role="system", content=system),
            Message(role="user", content="请综合上述结果，给出最终回答。"),
        ]

        response = self.brain.think(messages)
        return response.content

    @staticmethod
    def _extract_json_steps(text: str) -> list[str] | None:
        """从大脑回复中提取步骤列表，兼容多种格式"""
        for extract in [text, *re.findall(r"\{[\s\S]*?\}", text)]:
            try:
                data = json.loads(extract)
                steps = data.get("steps")
                if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                    return steps
            except json.JSONDecodeError:
                continue
        return None
