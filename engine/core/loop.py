"""智序者 Agent 主循环 —— 感知 → 思考 → 行动 → 记录

两种交互模式：
- 普通模式: 一问一答，可选工具调用（默认）
- 任务模式: 用户给目标，智序者自主规划步骤、逐步执行、综合结论（task 命令触发）
"""

from pathlib import Path

import json

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry
from engine.skills.registry import SkillRegistry
from engine.core.recorder import Recorder
from engine.core.react import react_loop, ConfirmCallback, StreamCallback, ToolEventCallback
from engine.core.task import TaskRunner
from engine.core.history import HistoryStore
from engine.core.memory_manager import MemoryManager
from engine.core.taxonomy import TaxonomyManager
from engine.core.profile import ProfileManager
from engine.config import config
from engine.log import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是智序者（zhixuzhe），一个以 DeepSeek 为基座的智能助手。

行为准则：
1. 回答简洁直接，不啰嗦
2. **绝不编造工具执行结果**：如果你没有调用工具或工具没有返回某信息，不要声称"我搜索了/查了/看了"然后给出臆测内容
3. 需要外部信息（天气、新闻、最新数据、代码库内容等）时，必须调用对应工具获取真实数据，不能凭记忆猜测
4. 工具返回什么就说什么，不在工具结果基础上添加未经验证的细节
5. 不知道就承认，不假装知道
6. 如果工具调用失败，明确告知用户失败原因，不要用想象的结果替代"""

# 自动任务模式判断提示词（普通对话入口的轻量判断）
AUTO_TASK_JUDGE = """你是任务复杂度判断器。判断用户请求是否需要进入"任务模式"执行。

任务模式 = 智序者自主规划多步骤、逐步执行（可能调用多个工具：网页搜索、执行命令、读写文件、抓取网页等），最后综合结论。
普通对话 = 直接回答，一问一答。

需要任务模式（输出 need_task: true）：
- 请求需要多步骤才能完成（调研、对比、分析、搭建、学习、排查等）
- 需要调用多个工具或需要真实外部数据
- 目标型请求（"帮我查一下...并总结"、"对比 A 和 B"、"搭建一个..."）

不需要任务模式（need_task: false）：
- 简单问答、闲聊、寒暄、常识问题
- 一句话能回答的问题

只输出 JSON，不要任何其他文字或 markdown 包裹：
{"need_task": true}
或
{"need_task": false}"""


def _show_help() -> None:
    print("命令：")
    print("  task <目标>   自主任务模式（规划→执行→综合）")
    print("  chain <目标> | <技能1> <技能2> ...   技能链式执行")
    print("  learn <主题ID>  从 GitHub 学习指定计算机知识主题")
    print("  taxonomy       列出可学习的知识分类")
    print("  profile        查看能力档案")
    print("  skills        列出已注册技能")
    print("  reset         重置对话历史")
    print("  help          显示此帮助")
    print("  exit          退出")
    print()
    print("安全提示：执行命令（run_shell）前会要求确认，输入 y 继续 / n 取消。")


class Agent:
    """智序者 Agent"""

    def __init__(
        self,
        brain: Brain,
        tools: ToolRegistry,
        recorder: Recorder,
        history_store: HistoryStore | None = None,
        skill_registry: SkillRegistry | None = None,
        memory_manager: MemoryManager | None = None,
        confirm_tools: set[str] | None = None,
        taxonomy: TaxonomyManager | None = None,
        profile_manager: ProfileManager | None = None,
    ):
        self.brain = brain
        self.tools = tools
        self.recorder = recorder
        self.history_store = history_store
        self.skill_registry = skill_registry
        self.memory_manager = memory_manager
        self.confirm_tools = confirm_tools or set()
        self.taxonomy = taxonomy
        self.profile_manager = profile_manager
        self.history: list[Message] = []
        self.system = Message(role="system", content=SYSTEM_PROMPT)
        self.task_runner = TaskRunner(
            brain, tools, recorder, skill_registry, memory_manager,
        )

        # 尝试恢复上次会话
        if history_store:
            latest = history_store.latest_session()
            if latest:
                self.history = history_store.load(latest)
                history_store.set_current_session(latest)
                logger.info(f"已恢复会话: {latest.name}（{len(self.history)} 条消息）")
            else:
                current = history_store.new_session()
                logger.info(f"无历史会话，新建: {current.name}")

    # ── 公共属性 ──

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @property
    def skill_count(self) -> int:
        return len(self.skill_registry) if self.skill_registry else 0

    # ── HITL 确认回调 ──

    def _hitl_confirm(self, tool_name: str, args: dict) -> bool:
        """交互式 HITL 确认"""
        if tool_name not in self.confirm_tools:
            return True

        args_str = " ".join(f"{k}={v}" for k, v in args.items())
        try:
            answer = input(f"\n  ⚠️  工具调用: {tool_name}({args_str})\n  → 执行? [y/N] ").strip().lower()
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── 自动任务模式判断 ──

    # 强任务信号：用户明确表达任务意图 → 直接进任务模式，零 LLM 判断
    _TASK_STRONG_HINTS = (
        "任务",            # "做个任务" / "执行任务" / "任务：" / "进入任务模式"
        "帮我做", "帮我完成", "帮我搞", "帮我实现",
        "帮我写个", "帮我写一个", "帮我搭建", "帮我部署",
        "做个", "搞个", "搭个", "部署一个", "实现一个",
        "调研一下", "对比一下", "分析一下",
    )

    # 强闲聊信号：明确非任务 → 直接普通对话，零 LLM 判断
    _CHAT_STRONG_HINTS = (
        "你好", "你好呀", "早上好", "下午好", "晚上好", "早安", "午安", "晚安",
        "再见", "拜拜", "谢谢你", "谢谢啦", "辛苦了", "在吗", "在吗？",
        "你是谁", "你叫什么", "hi", "hello", "hey", "thanks",
    )

    def should_auto_task(self, user_input: str) -> bool:
        """判断普通对话输入是否需要自动升级为任务模式。

        三层决策：
        1. 强任务信号（用户明确要任务）→ 直接 True，零 LLM 调用，秒进任务模式
        2. 强闲聊信号（明确非任务）→ 直接 False，零 LLM 调用
        3. 模棱两可 → Brain 轻量判断（不带工具、短提示词），输出 JSON
        判断失败或配置关闭时安全降级为普通对话（返回 False），不阻塞。
        """
        if not config.agent.auto_task:
            return False
        if not self.task_runner:
            return False

        text = user_input.strip().lower()
        # 第 1 层：强任务信号 → 直接命中，跳过 LLM
        for hint in self._TASK_STRONG_HINTS:
            if hint in text:
                logger.debug(f"强任务信号命中: {hint} ← {user_input[:40]}...")
                return True
        # 第 2 层：强闲聊信号 → 直接普通对话，跳过 LLM
        for hint in self._CHAT_STRONG_HINTS:
            if hint in text:
                logger.debug(f"强闲聊信号命中: {hint} ← {user_input[:40]}...")
                return False

        # 第 3 层：模棱两可 → Brain 轻量判断
        try:
            messages = [
                Message(role="system", content=AUTO_TASK_JUDGE),
                Message(role="user", content=user_input),
            ]
            response = self.brain.think(messages)
            text = response.content.strip()
            # 兼容 markdown 代码块包裹
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            data = json.loads(text)
            need = bool(data.get("need_task", False))
            logger.debug(f"自动任务判断: {need} ← {user_input[:40]}...")
            return need
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            logger.debug(f"自动任务判断失败，降级为普通对话: {e}")
            return False
        except Exception as e:
            logger.warning(f"自动任务判断异常，降级为普通对话: {e}")
            return False

    # ── 核心循环 ──

    def run(
        self,
        user_input: str,
        stream_callback: StreamCallback | None = None,
        confirm_callback: ConfirmCallback | None = None,
        tool_callback: ToolEventCallback | None = None,
    ) -> str:
        """单次交互：接收用户输入，返回响应。

        Args:
            user_input: 用户消息
            stream_callback: 可选流式回调。None 时默认 terminal 打印。
            confirm_callback: 可选 HITL 确认回调。显式传入 > CLI 默认 > None。
            tool_callback: 可选工具事件回调。工具调用前后触发，用于前端展示进度。
        """
        user_msg = Message(role="user", content=user_input)

        # 注入记忆上下文
        system_msg = self.system
        if self.memory_manager:
            ctx = self.memory_manager.build_context(user_input)
            if ctx:
                system_msg = Message(
                    role="system",
                    content=self.system.content + "\n\n" + ctx,
                )

        messages = [system_msg] + self.history + [user_msg]

        # 流式回调：未指定时用 terminal 打印
        if stream_callback is None:
            first = [True]

            def stream_print(chunk: str) -> None:
                if first[0]:
                    print("\n智序者 > ", end="", flush=True)
                    first[0] = False
                print(chunk, end="", flush=True)

            cb = stream_print
            is_cli = True
        else:
            cb = stream_callback
            is_cli = False

        # 确定 HITL 确认回调：显式传入 > CLI 默认 > None
        if confirm_callback is not None:
            hitl_cb = confirm_callback
        elif is_cli:
            hitl_cb = self._hitl_confirm
        else:
            hitl_cb = None

        # 收集本轮 ReAct 统计（用于判断是否触发经验反思）
        react_stats: dict = {}
        response = react_loop(
            self.brain, messages, self.tools,
            confirm_callback=hitl_cb,
            stream_callback=cb,
            tool_callback=tool_callback,
            stats=react_stats,
        )

        # CLI 模式换行
        if is_cli and not first[0]:
            print()

        # 记录
        self.history.append(user_msg)
        self.history.append(response)
        self.recorder.record(user_input, response.content)

        # 持久化对话历史
        if self.history_store:
            self.history_store.save(self.history)

        # 普通对话经验反思：有工具调用 = 做了实际操作，可能产生可复用教训
        # 纯文本闲聊/问答不触发，避免经验库膨胀
        tool_calls = react_stats.get("tool_calls", 0)
        if tool_calls > 0:
            logger.debug(f"普通对话触发经验反思（{tool_calls} 次工具调用）")
            try:
                self.task_runner.reflect_experience(user_input, response.content)
            except Exception as e:
                logger.debug(f"普通对话经验反思失败（不阻断主流程）: {e}")

        return response.content

    def interactive(self) -> None:
        """交互式 REPL"""
        print("智序者 v1 已启动。输入 help 查看命令，task <目标> 进入自主任务模式。\n")
        while True:
            try:
                user_input = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                logger.info("用户退出")
                print("\n再见。")
                break

            if not user_input:
                continue
            if user_input.lower() == "exit":
                logger.info("用户退出")
                print("再见。")
                break
            if user_input.lower() == "reset":
                self.history.clear()
                if self.history_store:
                    old_name = self.history_store.current_session_name or "?"
                    new = self.history_store.new_session()
                    logger.info(f"会话已重置: {old_name} → {new.name}")
                print("对话已重置。")
                continue
            if user_input.lower() == "help":
                _show_help()
                continue
            if user_input.lower() == "skills":
                if self.skill_registry and len(self.skill_registry) > 0:
                    print(f"\n已注册技能（{len(self.skill_registry)} 个）：\n"
                          f"{self.skill_registry.list_descriptions()}\n")
                else:
                    print("\n暂无注册技能。\n")
                continue

            if user_input.lower() == "taxonomy":
                if self.taxonomy:
                    print("\n═══ 知识分类（可学习主题） ═══\n")
                    for cat in self.taxonomy.categories:
                        print(f"  {cat.name}")
                        for node in cat.children:
                            done = ""
                            if self.profile_manager:
                                stats = self.profile_manager.get_language_stats(node.parent)
                                if stats.get("count", 0) > 0:
                                    done = " ✅"
                            print(f"    [{node.id}] {node.name} ({node.difficulty}){done}")
                    print()
                else:
                    print("\n知识分类系统未初始化。\n")
                continue

            if user_input.lower() == "profile":
                if self.profile_manager:
                    data = self.profile_manager.load()
                    print("\n═══ 智序者能力画像 ═══\n")
                    print("编程语言与领域：")
                    if data["languages"]:
                        for lang, stats in data["languages"].items():
                            print(f"  {lang:12s} {stats['level']:4s}  ({stats['count']} 条知识)  最近学习 {stats['last_study']}")
                    else:
                        print("  （暂无学习记录）")
                    print(f"\n技能：", end="")
                    if self.skill_registry:
                        print(", ".join(self.skill_registry.names()))
                    else:
                        print("无")
                    print()
                else:
                    print("\n能力档案未初始化。\n")
                continue

            if user_input.lower().startswith("learn "):
                node_id = user_input[6:].strip()
                if not self.taxonomy:
                    print("错误: 知识分类系统未初始化")
                    continue
                node = self.taxonomy.get_node(node_id)
                if not node:
                    print(f"错误: 未知主题 '{node_id}'。输入 taxonomy 查看可用主题。")
                    continue
                if not self.profile_manager:
                    print("错误: 能力档案未初始化")
                    continue

                # 检查是否已学过（复习模式）
                already_learned = self.profile_manager.has_topic(node.parent, node.name)
                mode_label = "复习" if already_learned else "新学"

                print("\n" + "═" * 44)
                print(f"  🎓 知识学习模式已启动（{mode_label}）")
                print(f"  📖 主题: {node.name}（{node.parent}，{node.difficulty}）")
                print("  🔍 智序者将搜索 GitHub、clone 仓库、阅读源码并沉淀知识")
                print("═" * 44 + "\n")

                # 使用罐装技能计划（而非LLM即兴规划），每步有明确成功条件
                from engine.skills.knowledge_learning.skill import (
                    KnowledgeLearningSkill,
                    is_learning_failed,
                )
                learn_skill = KnowledgeLearningSkill(
                    topic_name=node.name,
                    search_query=self.taxonomy.generate_search_query(node_id),
                    repo_hint=node.repo_hint or "",
                )
                plan = learn_skill.plan(node.name)
                goal = f"学习计算机知识主题：{node.name}（属于{node.parent}领域）"

                print(f"📋 罐装计划（{len(plan)}步，每步有明确成功标准）:")
                for i, s in enumerate(plan):
                    print(f"  [{i + 1}] {s[:70]}...")
                print()

                logger.info(f"开始学习({mode_label}): {node_id} ({node.name})")

                # 注入记忆上下文
                memory_context = ""
                if self.memory_manager:
                    memory_context = self.memory_manager.build_context(goal)

                # 执行计划（单步失败重试一次）
                step_results: list[str] = []
                response = ""
                for i, step in enumerate(plan):
                    step_ok = False
                    for attempt in range(2):  # 每步最多重试1次
                        try:
                            print(f"⏳ [{i + 1}/{len(plan)}] {step[:60]}...")
                            result = self.task_runner._execute_step(
                                goal, step, i, plan, step_results[:i],
                                self._hitl_confirm,
                                memory_context if i == 0 else "",
                            )
                            step_results.append(result)
                            print("✅")
                            step_ok = True
                            break
                        except Exception as e:
                            logger.warning(f"步骤 {i+1} 第{attempt+1}次尝试失败: {e}")
                            if attempt == 0:
                                print(f"⚠️  步骤 {i+1} 失败，重试一次...")
                            else:
                                step_results.append(f"执行失败（重试后仍失败）: {e}")
                                print(f"❌ 步骤 {i+1} 重试后仍失败，跳过继续")

                # 综合结论
                try:
                    response = self.task_runner._synthesize(goal, plan, step_results)
                except Exception as e:
                    response = f"学习过程部分失败，但已获取以下信息：\n\n" + "\n\n".join(
                        sr for sr in step_results if sr and not sr.startswith("执行失败")
                    )

                # 记录任务（无论成功失败都记录，便于复盘）
                try:
                    self.recorder.record_task(
                        goal, plan, step_results, response,
                        plan_source=f"skill:{learn_skill.name}",
                    )
                except Exception:
                    pass

                # 判断学习是否成功（方案B：材料步骤至少成功一个，失败步骤不过半）
                if is_learning_failed(step_results):
                    print(f"\n学习失败：未获取到可学习的材料或失败步骤过多，知识库和档案均未更新。\n")
                    continue

                print(f"\n═══ 学习成果 ═══\n\n{response}\n")

                # 写知识文件（幂等：覆盖已有知识文件）
                try:
                    self.recorder.record_knowledge(
                        parent=node.parent,
                        topic=node.name,
                        report=response,
                    )
                except Exception as e:
                    logger.debug(f"知识写入失败（不阻断流程）: {e}")

                # 更新能力档案（幂等：重复学习不重复计数）
                try:
                    result = self.profile_manager.record_learning(
                        parent=node.parent,
                        topic=node.name,
                        summary=response[:200],
                    )
                    action = "新学" if result["is_new"] else "复习"
                    print(f"[档案已更新] {action} {node.parent} {node.name} → {result['level']}（{result['count']} 条）\n")
                except Exception as e:
                    logger.debug(f"档案更新失败（不阻断流程）: {e}")

                # 反思经验
                try:
                    self.task_runner.reflect_experience(goal, response)
                except Exception:
                    pass

                continue

            # 任务模式
            if user_input.lower().startswith("task "):
                goal = user_input[5:].strip()
                if not goal:
                    print("用法: task <目标描述>")
                    continue
                logger.info(f"进入任务模式: {goal[:50]}...")
                print("\n" + "═" * 44)
                print("  🔧 任务模式已启动")
                print("  📋 智序者将自主规划步骤、逐步执行（可能调用多个工具），完成后给出综合结论")
                print("  ⏸  如需中途停止，按 Ctrl+C 可退出")
                print("═" * 44)
                print(f"  🎯 目标: {goal}\n")
                response = self.task_runner.run(
                    goal,
                    confirm_callback=self._hitl_confirm,
                )
                print(f"\n═══ 最终结论 ═══\n\n{response}\n")
                # 任务结果入历史，让后续对话知道刚执行过什么
                self.history.append(Message(role="user", content=user_input))
                self.history.append(Message(role="assistant", content=response))
                if self.history_store:
                    self.history_store.save(self.history)
                continue

            # 链式模式: chain <目标> | <技能1> <技能2> ...
            if user_input.lower().startswith("chain "):
                rest = user_input[6:]
                if "|" not in rest:
                    print('用法: chain <目标> | <技能1> <技能2> ...')
                    continue
                goal_part, skills_part = rest.split("|", 1)
                goal = goal_part.strip()
                skill_names = skills_part.split()
                if not goal or not skill_names:
                    print('用法: chain <目标> | <技能1> <技能2> ...')
                    continue
                if not self.skill_registry or len(self.skill_registry) == 0:
                    print("错误: 无已注册技能，无法执行链式任务")
                    continue
                logger.info(f"进入链式模式: {goal[:50]} | {skill_names}")
                print("\n" + "═" * 44)
                print("  🔗 链式任务模式已启动")
                print(f"  🧩 技能链: {' → '.join(skill_names)}")
                print("═" * 44)
                print(f"  🎯 目标: {goal}\n")
                from engine.core.orchestrator import SkillChain
                chain = SkillChain(
                    self.brain, self.tools, self.recorder,
                    self.skill_registry, self.memory_manager,
                )
                response = chain.run(
                    goal, skill_names,
                    confirm_callback=self._hitl_confirm,
                )
                print(f"\n═══ 链式结论 ═══\n\n{response}\n")
                # 链式结果入历史
                self.history.append(Message(role="user", content=user_input))
                self.history.append(Message(role="assistant", content=response))
                if self.history_store:
                    self.history_store.save(self.history)
                continue

            # 普通对话（已在 run() 内流式输出，这里不重复打印）
            # 先判断是否自动升级为任务模式
            if self.should_auto_task(user_input):
                logger.info(f"自动升级为任务模式: {user_input[:50]}...")
                print("\n" + "═" * 44)
                print("  🔧 检测到该请求需要多步骤执行，智序者已自动进入任务模式")
                print("  📋 将自主规划步骤、逐步执行（可能调用多个工具），完成后给出综合结论")
                print("═" * 44 + "\n")
                response = self.task_runner.run(
                    user_input,
                    confirm_callback=self._hitl_confirm,
                )
                print(f"\n═══ 最终结论 ═══\n\n{response}\n")
                self.history.append(Message(role="user", content=user_input))
                self.history.append(Message(role="assistant", content=response))
                if self.history_store:
                    self.history_store.save(self.history)
                continue

            self.run(user_input)
