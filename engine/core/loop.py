"""智序者 Agent 主循环 —— 感知 → 思考 → 行动 → 记录

两种交互模式：
- 普通模式: 一问一答，可选工具调用（默认）
- 任务模式: 用户给目标，智序者自主规划步骤、逐步执行、综合结论（task 命令触发）
"""

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry
from engine.skills.registry import SkillRegistry
from engine.core.recorder import Recorder
from engine.core.react import react_loop
from engine.core.task import TaskRunner
from engine.core.history import HistoryStore

SYSTEM_PROMPT = """你是智序者（zhixuzhe），一个以 DeepSeek 为基座的智能助手。

行为准则：
- 回答简洁直接，不啰嗦
- 能用工具获取的信息就不猜测
- 不知道就承认，不假装知道"""

MAX_TOOL_ROUNDS = 5


def _show_help() -> None:
    print("命令：")
    print("  task <目标>   自主任务模式（规划→执行→综合）")
    print("  skills        列出已注册技能")
    print("  reset         重置对话历史")
    print("  help          显示此帮助")
    print("  exit          退出")
    print()


class Agent:
    """智序者 Agent"""

    def __init__(
        self,
        brain: Brain,
        tools: ToolRegistry,
        recorder: Recorder,
        history_store: HistoryStore | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.brain = brain
        self.tools = tools
        self.recorder = recorder
        self.history_store = history_store
        self.skill_registry = skill_registry
        self.history: list[Message] = []
        self.system = Message(role="system", content=SYSTEM_PROMPT)
        self.task_runner = TaskRunner(brain, tools, recorder, skill_registry)

        # 尝试恢复上次会话
        if history_store:
            latest = history_store.latest_session()
            if latest:
                self.history = history_store.load(latest)
                history_store._current = latest
                print(f"[HistoryStore] 已恢复会话: {latest.name} "
                      f"（{len(self.history)} 条消息）")
            else:
                current = history_store.new_session()
                print(f"[HistoryStore] 无历史会话，新建: {current.name}")

    def run(self, user_input: str) -> str:
        """单次交互：接收用户输入，返回响应"""
        user_msg = Message(role="user", content=user_input)
        messages = [self.system] + self.history + [user_msg]

        response = react_loop(self.brain, messages, self.tools, MAX_TOOL_ROUNDS)

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
        print("智序者已启动。输入 help 查看命令，task <目标> 进入自主任务模式。\n")
        while True:
            try:
                user_input = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。")
                break

            if not user_input:
                continue
            if user_input.lower() == "exit":
                print("再见。")
                break
            if user_input.lower() == "reset":
                self.history.clear()
                if self.history_store:
                    old_name = self.history_store._current.name if self.history_store._current else "?"
                    new = self.history_store.new_session()
                    print(f"[HistoryStore] 会话已重置: {old_name} → {new.name}")
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

            # 任务模式
            if user_input.lower().startswith("task "):
                goal = user_input[5:].strip()
                if not goal:
                    print("用法: task <目标描述>")
                    continue
                response = self.task_runner.run(goal)
                print(f"\n═══ 最终结论 ═══\n\n{response}\n")
                continue

            # 普通对话
            response = self.run(user_input)
            print(f"\n智序者 > {response}\n")
