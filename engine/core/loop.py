"""智序者 Agent 主循环 —— 感知 → 思考 → 行动 → 记录

两种交互模式：
- 普通模式: 一问一答，可选工具调用（默认）
- 任务模式: 用户给目标，智序者自主规划步骤、逐步执行、综合结论（task 命令触发）
"""

from pathlib import Path

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
- 回答简洁直接，不啰嗦
- 能用工具获取的信息就不猜测
- 不知道就承认，不假装知道"""


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

        response = react_loop(
            self.brain, messages, self.tools,
            confirm_callback=hitl_cb,
            stream_callback=cb,
            tool_callback=tool_callback,
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

                print(f"\n🎓 开始学习: {node.name} ({node.parent}, {node.difficulty})")
                print(f"   将搜索 GitHub 并深入阅读源码...\n")

                # 构造学习目标
                goal = (
                    f"学习计算机知识主题：{node.name}（属于{node.parent}领域）。\n"
                    f"搜索提示：{self.taxonomy.generate_search_query(node_id)}\n"
                    f"{'推荐仓库：' + node.repo_hint if node.repo_hint else ''}\n\n"
                    f"要求：\n"
                    f"1. 用 web_search 在 GitHub 上找到该主题最权威/最活跃的 1 个开源仓库（优先官方仓库或知名社区仓库，要求 README 完整、最近 6 个月有 commit）\n"
                    f"2. 用 run_shell 将仓库 git clone --depth 1 到 memory/knowledge/repos/ 目录\n"
                    f"3. 用 run_shell 查看仓库结构，用 read_file 阅读核心源码文件（入口、核心模块，最多 5 个文件）\n"
                    f"4. 提炼学习成果并输出结构化报告，包含：\n"
                    f"   - 核心概念与设计模式\n"
                    f"   - 值得借鉴的代码范式（学模式不抄代码）\n"
                    f"   - 安全边界与常见踩坑点\n"
                    f"   - 对智序者的启发\n"
                    f"5. 学习完成后自动更新能力档案"
                )

                logger.info(f"开始学习: {node_id} ({node.name})")
                response = self.task_runner.run(
                    goal,
                    confirm_callback=self._hitl_confirm,
                )
                print(f"\n═══ 学习成果 ═══\n\n{response}\n")

                # 更新能力档案
                try:
                    stats = self.profile_manager.get_language_stats(node.parent)
                    new_count = stats["count"] + 1
                    self.profile_manager.record_learning(
                        parent=node.parent,
                        topic=node.name,
                        total_count=new_count,
                        summary=response[:200],
                    )
                    print(f"[能力档案已更新] {node.parent} 现在 {node.name} → {ProfileManager.level(new_count)}（{new_count} 条）\n")
                except Exception as e:
                    logger.debug(f"档案更新失败（不阻断学习流程）: {e}")

                # 入历史
                self.history.append(Message(role="user", content=user_input))
                self.history.append(Message(role="assistant", content=response))
                if self.history_store:
                    self.history_store.save(self.history)
                continue

            # 任务模式
            if user_input.lower().startswith("task "):
                goal = user_input[5:].strip()
                if not goal:
                    print("用法: task <目标描述>")
                    continue
                logger.info(f"进入任务模式: {goal[:50]}...")
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
            self.run(user_input)
