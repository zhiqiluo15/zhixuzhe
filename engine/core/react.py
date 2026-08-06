"""ReAct 循环 —— 思考 → 工具调用 → 执行 → 再思考

Agent 普通对话和 TaskRunner 步骤执行共用此循环，
避免重复实现。
"""

import json
from typing import Callable

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry
from engine.config import config
from engine.log import get_logger

logger = get_logger(__name__)

# HITL 回调类型：接收 (tool_name, args_dict)，返回 True=允许执行, False=取消
ConfirmCallback = Callable[[str, dict], bool]


def react_loop(
    brain: Brain,
    messages: list[Message],
    tools: ToolRegistry,
    max_rounds: int | None = None,
    confirm_callback: ConfirmCallback | None = None,
) -> Message:
    """执行一次 ReAct 循环：思考 → 工具调用 → 执行 → 再思考，返回最终 Message。

    Args:
        max_rounds: 最大工具调用轮次，None 则使用 config.agent.max_tool_rounds
        confirm_callback: 可选 HITL 确认回调。
    """
    if max_rounds is None:
        max_rounds = config.agent.max_tool_rounds

    tool_specs = tools.to_openai_specs() or None
    response = brain.think(messages, tool_specs)

    for round_i in range(max_rounds):
        if not response.tool_calls:
            break

        messages.append(response)
        for tc in response.tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            logger.debug(f"工具调用 [轮次 {round_i + 1}]: {name}({args})")

            # HITL 确认
            if confirm_callback is not None and not confirm_callback(name, args):
                result = f"[已取消] 用户拒绝了工具调用: {name}"
            else:
                result = tools.execute(name, **args)

            max_chars = config.agent.max_tool_output_chars
            if len(result) > max_chars:
                result = result[:max_chars] + (
                    f"\n\n[已截断，原长度 {len(result)} 字符]"
                )
            messages.append(Message(
                role="tool",
                content=result,
                tool_call_id=tc["id"],
            ))

        response = brain.think(messages, tool_specs)

    return response
