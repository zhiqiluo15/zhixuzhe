"""ContextCompressor 上下文压缩测试

验证增量分层摘要：短历史不压缩、超阈值触发、增量合并、reset 重置、关闭开关、失败降级。
纯本地运行，用 MockBrain 模拟摘要输出，不依赖 DeepSeek API。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.brain.base import Brain, Message
from engine.core.compress import ContextCompressor


class MockBrain(Brain):
    """模拟大脑：记录每次 think 的 user prompt，返回固定摘要"""

    def __init__(self, response: str = "（摘要内容）"):
        self.response = response
        self.calls: list[str] = []  # 每次 think 的 user prompt
        self.fail = False

    def think(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        self.calls.append(messages[-1].content if messages else "")
        if self.fail:
            raise RuntimeError("brain unavailable")
        return Message(role="assistant", content=self.response)


def _make_history(n: int) -> list[Message]:
    """构造 n 条交替 user/assistant 消息"""
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append(Message(role=role, content=f"消息{i}"))
    return msgs


def _make_compressor(brain: MockBrain, **kw) -> ContextCompressor:
    kw.setdefault("keep_recent", 4)
    kw.setdefault("summarize_chunk", 4)
    kw.setdefault("max_summary_chars", 500)
    return ContextCompressor(brain, **kw)


def test_no_compress_when_short_history():
    """历史未超阈值：不调用 Brain，返回原样消息列表"""
    brain = MockBrain()
    comp = _make_compressor(brain)
    system = Message(role="system", content="系统提示")
    user = Message(role="user", content="你好")
    history = _make_history(4)  # len == keep_recent

    result = comp.build(history, system, user)

    assert brain.calls == [], "短历史不应触发摘要"
    assert len(result) == 6  # system + 4 历史 + user
    assert result[0] is system and result[-1] is user


def test_compress_triggers_when_over_threshold():
    """历史超阈值：触发一次摘要，摘要作为 system 消息注入"""
    brain = MockBrain(response="用户问了 4 个问题")
    comp = _make_compressor(brain)
    system = Message(role="system", content="系统提示")
    user = Message(role="user", content="新问题")
    history = _make_history(8)  # cut = 8 - 4 = 4 == chunk → 恰好 1 块

    result = comp.build(history, system, user)

    assert len(brain.calls) == 1, "超阈值应触发 1 次摘要调用"
    assert len(result) == 7  # system + 摘要 + 最近 4 条 + user
    assert result[0] is system
    assert result[1].role == "system"
    assert "历史对话摘要" in result[1].content
    assert "用户问了 4 个问题" in result[1].content
    # 最近的 4 条历史完整保留
    assert result[2].content == "消息4" and result[5].content == "消息7"
    assert result[-1] is user


def test_incremental_summarize_merges_existing():
    """增量：新增长的部分只摘要新增块，且 Brain 收到已有摘要用于合并"""
    brain = MockBrain(response="合并后的摘要")
    comp = _make_compressor(brain)
    system = Message(role="system", content="系统提示")

    comp.build(_make_history(8), system, Message(role="user", content="q1"))
    assert len(brain.calls) == 1
    first_prompt = brain.calls[0]
    assert "（无）" in first_prompt, "首次摘要应无已有摘要"

    comp.build(_make_history(12), system, Message(role="user", content="q2"))
    assert len(brain.calls) == 2, "第二次应再触发 1 次增量摘要"
    second_prompt = brain.calls[1]
    assert "合并后的摘要" in second_prompt, "增量摘要应携带已有摘要供合并"
    assert "消息4" in second_prompt and "消息7" in second_prompt, "新块内容应传给 Brain"


def test_recent_window_preserved():
    """保留窗口：最早超限部分被摘要，最近 keep_recent 条完整保留"""
    brain = MockBrain()
    comp = _make_compressor(brain)
    system = Message(role="system", content="系统提示")
    history = _make_history(12)  # cut = 8，分块 4+4 → 2 次摘要调用
    user = Message(role="user", content="q")

    result = comp.build(history, system, user)

    assert len(brain.calls) == 2, "12 条历史、cut=8 → 2 块各 4 条"
    # 覆盖前 8 条（2 块），保留最近 4 条 + user
    assert comp._summarized_upto == 8
    assert len(result) == 7  # system + 摘要 + 4 历史 + user
    assert result[2].content == "消息8"
    assert result[-2].content == "消息11"
    assert result[-1] is user


def test_reset_clears_summary_state():
    """reset 后摘要状态清空：同一份长历史会重新触发摘要"""
    brain = MockBrain()
    comp = _make_compressor(brain)
    system = Message(role="system", content="系统提示")
    history = _make_history(8)

    comp.build(history, system, Message(role="user", content="q1"))
    assert len(brain.calls) == 1

    comp.reset()
    comp.build(history, system, Message(role="user", content="q2"))
    assert len(brain.calls) == 2, "reset 后应重新摘要"
    assert comp._summarized_upto == 4


def test_disabled_returns_original():
    """enabled=False：完全不做压缩，不调用 Brain"""
    brain = MockBrain()
    comp = _make_compressor(brain, enabled=False)
    system = Message(role="system", content="系统提示")
    user = Message(role="user", content="你好")
    history = _make_history(20)

    result = comp.build(history, system, user)

    assert brain.calls == []
    assert len(result) == 22  # system + 20 历史 + user
    assert result[1] is history[0]


def test_summarize_failure_degrades_gracefully():
    """摘要调用失败：安全降级为不压缩，不阻断主流程"""
    brain = MockBrain()
    comp = _make_compressor(brain)
    system = Message(role="system", content="系统提示")
    user = Message(role="user", content="你好")
    history = _make_history(8)

    brain.fail = True
    result = comp.build(history, system, user)

    assert len(result) == 10  # 原样返回 system + 8 历史 + user
    assert result[0] is system and result[-1] is user
    assert comp._summary == ""
    assert comp._summarized_upto == 0
