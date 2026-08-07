"""ReAct 循环 —— 思考 → 工具调用 → 执行 → 再思考

Agent 普通对话和 TaskRunner 步骤执行共用此循环，
避免重复实现。

支持流式输出：传入 stream_callback 时，每轮思考的文本块会实时回调。
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

# 流式回调类型：接收文本块（str），用于实时显示
StreamCallback = Callable[[str], None]


def _get_response(
    brain: Brain,
    messages: list[Message],
    tool_specs: list[dict] | None,
    stream_callback: StreamCallback | None,
) -> Message:
    """获取一轮思考结果。有 stream_callback 时走流式，否则走普通 think。"""
    if stream_callback is None:
        return brain.think(messages, tool_specs)

    # 流式模式
    response = None
    for chunk_type, data in brain.think_stream(messages, tool_specs):
        if chunk_type == "text":
            stream_callback(str(data))
        elif chunk_type == "done":
            response = data
            break

    if response is None:
        response = Message(role="assistant", content="[流式响应异常：未收到 done 信号]")
    return response


def react_loop(
    brain: Brain,
    messages: list[Message],
    tools: ToolRegistry,
    max_rounds: int | None = None,
    confirm_callback: ConfirmCallback | None = None,
    stream_callback: StreamCallback | None = None,
) -> Message:
    """执行一次 ReAct 循环：思考 → 工具调用 → 执行 → 再思考，返回最终 Message。

    Args:
        max_rounds: 最大工具调用轮次，None 则使用 config.agent.max_tool_rounds
        confirm_callback: 可选 HITL 确认回调
        stream_callback: 可选流式回调，每收到一个 token 文本块时触发
    """
    if max_rounds is None:
        max_rounds = config.agent.max_tool_rounds

    tool_specs = tools.to_openai_specs() or None

    # 首轮思考
    response = _get_response(brain, messages, tool_specs, stream_callback)

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

        # 下一轮思考（工具结果已加入 messages）
        response = _get_response(brain, messages, tool_specs, stream_callback)

    # 轮次耗尽但 Brain 仍想调工具：清空 tool_calls 并标注，
    # 避免半成品 tool_calls 被存入 history 造成后续上下文混乱。
    if response.tool_calls:
        logger.warning(
            f"达到最大工具调用轮次 {max_rounds}，剩余 tool_calls 被丢弃"
        )
        response = Message(
            role="assistant",
            content=(response.content or "") + (
                "\n\n[已达到最大工具调用轮次，部分工具调用未执行]"
            ),
            tool_calls=None,
        )

    # 流式模式下，最终 response 已在流式过程中逐块输出过，
    # 这里不再重复输出，由调用方决定如何处理。
    return response
