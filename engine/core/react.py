"""ReAct 循环 —— 思考 → 工具调用 → 执行 → 再思考

Agent 普通对话和 TaskRunner 步骤执行共用此循环，
避免重复实现。
"""

import json
from typing import Callable

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry

DEFAULT_MAX_ROUNDS = 5
MAX_TOOL_OUTPUT_CHARS = 32000  # 单次工具输出最大字符数，防止撑爆上下文

# HITL 回调类型：接收 (tool_name, args_dict)，返回 True=允许执行, False=取消
ConfirmCallback = Callable[[str, dict], bool]


def react_loop(
    brain: Brain,
    messages: list[Message],
    tools: ToolRegistry,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    confirm_callback: ConfirmCallback | None = None,
) -> Message:
    """执行一次 ReAct 循环：思考 → 工具调用 → 执行 → 再思考，返回最终 Message。

    Args:
        confirm_callback: 可选 HITL 确认回调。每次工具调用前触发，
                         返回 False 则跳过该工具（返回取消消息）。
    """
    tool_specs = tools.to_openai_specs() or None
    response = brain.think(messages, tool_specs)

    for _ in range(max_rounds):
        if not response.tool_calls:
            break

        messages.append(response)
        for tc in response.tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            # HITL 确认
            if confirm_callback is not None and not confirm_callback(name, args):
                result = f"[已取消] 用户拒绝了工具调用: {name}"
            else:
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
