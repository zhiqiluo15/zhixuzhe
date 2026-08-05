"""ReAct 循环 —— 思考 → 工具调用 → 执行 → 再思考

Agent 普通对话和 TaskRunner 步骤执行共用此循环，
避免重复实现。
"""

import json

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry

DEFAULT_MAX_ROUNDS = 5
MAX_TOOL_OUTPUT_CHARS = 32000  # 单次工具输出最大字符数，防止撑爆上下文


def react_loop(
    brain: Brain,
    messages: list[Message],
    tools: ToolRegistry,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> Message:
    """执行一次 ReAct 循环：思考 → 工具调用 → 执行 → 再思考，返回最终 Message。

    调用方负责构造好初始 messages（含 system prompt + user input），
    本函数只负责工具调用循环部分。
    """
    tool_specs = tools.to_openai_specs() or None
    response = brain.think(messages, tool_specs)

    for _ in range(max_rounds):
        if not response.tool_calls:
            break

        messages.append(response)
        for tc in response.tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            result = tools.execute(name, **args)
            # 截断过长输出，防止撑爆上下文窗口
            if len(result) > MAX_TOOL_OUTPUT_CHARS:
                result = result[:MAX_TOOL_OUTPUT_CHARS] + (
                    f"\n\n[已截断，原长度 {len(result)} 字符]"
                )
            messages.append(Message(
                role="tool",
                content=result,
                tool_call_id=tc["id"],
            ))

        response = brain.think(messages, tool_specs)

    return response
