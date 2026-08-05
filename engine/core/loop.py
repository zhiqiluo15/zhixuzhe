"""智序者 Agent 主循环 —— 感知 → 思考 → 行动 → 记录

两种交互模式：
- 普通模式: 一问一答，可选工具调用（默认）
- 任务模式: 用户给目标，智序者自主规划步骤、逐步执行、综合结论（task 命令触发）
"""

import json

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry
from engine.core.recorder import Recorder
from engine.core.task import TaskRunner

SYSTEM_PROMPT = """你是智序者（zhixuzhe），一个以 DeepSeek 为基座的智能助手。

行为准则：
- 回答简洁直接，不啰嗦
- 能用工具获取的信息就不猜测
- 不知道就承认，不假装知道"""

MAX_TOOL_ROUNDS = 5


def _show_help() -> None:
    print("命令：")
    print("  task <目标>   自主任务模式（规划→执行→综合）")
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
    ):
        self.brain = brain
        self.tools = tools
        self.recorder = recorder
        self.history: list[Message] = []
        self.system = Message(role="system", content=SYSTEM_PROMPT)
        self.task_runner = TaskRunner(brain, tools, recorder)

    def run(self, user_input: str) -> str:
        """单次交互：接收用户输入，返回响应"""
        user_msg = Message(role="user", content=user_input)
        messages = [self.system] + self.history + [user_msg]

        tool_specs = self.tools.to_openai_specs() or None
        response = self.brain.think(messages, tool_specs)

        # 工具调用循环
        for _ in range(MAX_TOOL_ROUNDS):
            if not response.tool_calls:
                break

            messages.append(response)
            for tc in response.tool_calls:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                result = self.tools.execute(name, **args)
                messages.append(Message(
                    role="tool",
                    content=result,
                    tool_call_id=tc["id"],
                ))

            response = self.brain.think(messages, tool_specs)

        # 记录
        self.history.append(user_msg)
        self.history.append(response)
        self.recorder.record(user_input, response.content)

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
                print("对话已重置。")
                continue
            if user_input.lower() == "help":
                _show_help()
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
