"""智序者 Agent 主循环 —— 感知 → 思考 → 行动 → 记录"""

import json

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry
from engine.core.recorder import Recorder

SYSTEM_PROMPT = """你是智序者（zhixuzhe），一个以 DeepSeek 为基座的智能助手。

行为准则：
- 回答简洁直接，不啰嗦
- 能用工具获取的信息就不猜测
- 不知道就承认，不假装知道"""

MAX_TOOL_ROUNDS = 5


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
        print("智序者已启动。输入 exit 退出，reset 重置对话。\n")
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

            response = self.run(user_input)
            print(f"\n智序者 > {response}\n")
