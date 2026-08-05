"""测试重构后的 react_loop / Agent / TaskRunner 逻辑

纯本地运行，不依赖 DeepSeek API。
模拟 Brain 会按预设序列返回响应（含工具调用），验证各组件行为。

用法：从项目根运行 `python engine/tests/test_react.py`
"""

import sys
from pathlib import Path

# 确保项目根在 sys.path 开头
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry, Tool
from engine.core.recorder import Recorder
from engine.core.react import react_loop
from engine.core.loop import Agent
from engine.core.task import TaskRunner
from engine.core.history import HistoryStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ═══════════════════════════════════════════
# 模拟 Brain：按预设序列返回响应
# ═══════════════════════════════════════════

class MockBrain(Brain):
    """模拟大脑，不联网，按预设序列逐次返回 responses"""

    def __init__(self, responses: list[Message]):
        self.responses = responses
        self.calls: list[dict] = []  # 记录每次 think 的调用参数
        self._last_messages: list[Message] = []

    def think(self, messages: list[Message], tools: list[dict] | None = None) -> Message:
        self._last_messages = messages
        self.calls.append({
            "msg_count": len(messages),
            "has_tools": tools is not None,
            "last_role": messages[-1].role if messages else "none",
        })
        if not self.responses:
            return Message(role="assistant", content="（大脑无更多响应）")
        return self.responses.pop(0)

    def last_roles(self) -> list[str]:
        """返回最后一次 think 调用时 messages 中各消息的 role 列表（测试断言用）"""
        return [m.role for m in self._last_messages]


# ═══════════════════════════════════════════
# 模拟工具
# ═══════════════════════════════════════════

def mock_add(a: int, b: int) -> str:
    return str(a + b)


def mock_weather(city: str) -> str:
    return f"{city}：晴，25°C"


def build_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(
        name="add",
        description="两数相加",
        func=mock_add,
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "第一个数"},
                "b": {"type": "integer", "description": "第二个数"},
            },
            "required": ["a", "b"],
        },
    ))
    registry.register(Tool(
        name="get_weather",
        description="查询城市天气",
        func=mock_weather,
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"},
            },
            "required": ["city"],
        },
    ))
    return registry


# ═══════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════

def test_react_loop_no_tools():
    """react_loop：大脑直接回答，不调工具"""
    print("=" * 50)
    print("测试 1: react_loop 无工具调用")
    brain = MockBrain([
        Message(role="assistant", content="你好，我是智序者。"),
    ])
    tools = build_tools()
    messages = [
        Message(role="system", content="你是智序者。"),
        Message(role="user", content="你好"),
    ]

    result = react_loop(brain, messages, tools, max_rounds=5)

    assert result.role == "assistant"
    assert "智序者" in result.content
    assert result.tool_calls is None
    assert len(brain.calls) == 1  # 只调用一次 think
    print("  ✅ 通过：直接回答，无工具调用，think 调用 1 次")


def test_react_loop_with_tool():
    """react_loop：大脑调工具 → 收到结果 → 最终回答"""
    print("\n" + "=" * 50)
    print("测试 2: react_loop 带工具调用")
    brain = MockBrain([
        # 第 1 轮：决定调 add 工具
        Message(
            role="assistant",
            content="",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "add",
                    "arguments": '{"a": 3, "b": 5}',
                },
            }],
        ),
        # 第 2 轮：收到工具结果后回答
        Message(role="assistant", content="3 + 5 = 8"),
    ])
    tools = build_tools()
    messages = [
        Message(role="system", content="你是数学助手。"),
        Message(role="user", content="3加5等于几？"),
    ]

    result = react_loop(brain, messages, tools, max_rounds=5)

    assert result.role == "assistant"
    assert "8" in result.content
    assert result.tool_calls is None
    assert len(brain.calls) == 2  # 两轮 think
    # 第 2 轮调用时 messages 应包含 tool 角色消息
    assert "tool" in brain.last_roles()
    print("  ✅ 通过：调工具→收结果→最终回答，think 调用 2 次")


def test_react_loop_multi_tool():
    """react_loop：多轮工具调用"""
    print("\n" + "=" * 50)
    print("测试 3: react_loop 多轮工具调用")
    brain = MockBrain([
        # 第 1 轮：调 add
        Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_1", "type": "function",
                "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'},
            }],
        ),
        # 第 2 轮：再调 get_weather
        Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_2", "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "北京"}'},
            }],
        ),
        # 第 3 轮：最终回答
        Message(role="assistant", content="1+2=3，北京今天晴，25°C"),
    ])
    tools = build_tools()
    messages = [
        Message(role="system", content="你是全能助手。"),
        Message(role="user", content="算1+2并查北京天气"),
    ]

    result = react_loop(brain, messages, tools, max_rounds=5)

    assert result.role == "assistant"
    assert "3" in result.content and "北京" in result.content
    assert len(brain.calls) == 3
    print("  ✅ 通过：两轮工具调用→最终回答，think 调用 3 次")


def test_agent_normal_mode():
    """Agent 普通对话模式"""
    print("\n" + "=" * 50)
    print("测试 4: Agent 普通对话")
    brain = MockBrain([
        Message(role="assistant", content="我叫智序者，有什么可以帮你的？"),
    ])
    tools = build_tools()
    recorder = Recorder(root=PROJECT_ROOT)
    agent = Agent(brain=brain, tools=tools, recorder=recorder)

    response = agent.run("你是谁？")

    assert "智序者" in response
    assert len(agent.history) == 2  # user + assistant
    print("  ✅ 通过：普通对话正常，历史记录正确")


def test_agent_tool_mode():
    """Agent 带工具调用"""
    print("\n" + "=" * 50)
    print("测试 5: Agent 对话中触发工具调用")
    brain = MockBrain([
        Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_1", "type": "function",
                "function": {"name": "add", "arguments": '{"a": 10, "b": 20}'},
            }],
        ),
        Message(role="assistant", content="10 + 20 = 30"),
    ])
    tools = build_tools()
    recorder = Recorder(root=PROJECT_ROOT)
    agent = Agent(brain=brain, tools=tools, recorder=recorder)

    response = agent.run("10加20等于几？")

    assert "30" in response
    print("  ✅ 通过：Agent 工具调用正常")


def test_task_runner():
    """TaskRunner 自主任务模式"""
    print("\n" + "=" * 50)
    print("测试 6: TaskRunner 自主任务（规划→执行→综合）")

    brain = MockBrain([
        # _plan 调用：返回步骤
        Message(role="assistant", content='{"steps": ["计算 3+5", "查询北京天气"]}'),
        # _execute_step 第 1 步：调 add
        Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_a", "type": "function",
                "function": {"name": "add", "arguments": '{"a": 3, "b": 5}'},
            }],
        ),
        # _execute_step 第 1 步：收到结果后回答
        Message(role="assistant", content="3 + 5 = 8"),
        # _execute_step 第 2 步：调 get_weather
        Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_w", "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "北京"}'},
            }],
        ),
        # _execute_step 第 2 步：收到结果后回答
        Message(role="assistant", content="北京天气晴，25°C"),
        # _synthesize 调用
        Message(role="assistant", content="综合结论：3+5=8，北京晴25°C，任务完成。"),
    ])
    tools = build_tools()
    recorder = Recorder(root=PROJECT_ROOT)

    runner = TaskRunner(brain=brain, tools=tools, recorder=recorder)
    result = runner.run("计算并查天气", verbose=False)

    assert "8" in result and "北京" in result
    print(f"  结论: {result[:80]}...")
    print("  ✅ 通过：TaskRunner 规划→执行→综合全链路正常")


def test_task_runner_plan_fallback():
    """TaskRunner 规划解析失败兜底"""
    print("\n" + "=" * 50)
    print("测试 7: TaskRunner 规划解析失败 → 兜底单步")

    brain = MockBrain([
        # _plan 第 1 次：返回无效格式
        Message(role="assistant", content="我想想..."),
        # _plan 第 2 次：继续无效
        Message(role="assistant", content="嗯，应该这样做..."),
        # _plan 第 3 次：依然无效 → 兜底
        Message(role="assistant", content="还是不行..."),
        # 兜底后 _execute_step 第 1 步（goal 作为单步）
        Message(role="assistant", content="无法分解，但可以帮你。"),
        # _synthesize
        Message(role="assistant", content="兜底结论：无法自动分解任务。"),
    ])
    tools = build_tools()
    recorder = Recorder(root=PROJECT_ROOT)

    runner = TaskRunner(brain=brain, tools=tools, recorder=recorder)
    result = runner.run("一个无法自动分解的复杂目标", verbose=False)

    assert isinstance(result, str) and len(result) > 0
    print(f"  兜底结论: {result}")
    print("  ✅ 通过：规划失败兜底正常，未崩溃")


# ═══════════════════════════════════════════
# HistoryStore 测试
# ═══════════════════════════════════════════

import shutil as _shutil
_conv_dir = PROJECT_ROOT / "memory" / "conversations"


def _clean_conversations():
    """清理会话文件确保测试隔离"""
    if _conv_dir.exists():
        _shutil.rmtree(_conv_dir)


def test_history_save_load():
    """HistoryStore 基本存取"""
    _clean_conversations()
    print("\n" + "=" * 50)
    print("测试 8: HistoryStore 保存和加载")
    store = HistoryStore(root=PROJECT_ROOT)
    store.new_session()

    msgs = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好，我是智序者。"),
    ]
    store.save(msgs)

    loaded = store.load(store._current)
    assert len(loaded) == 2
    assert loaded[0].role == "user"
    assert loaded[0].content == "你好"
    assert loaded[1].role == "assistant"
    assert "智序者" in loaded[1].content
    print("  ✅ 通过：保存 2 条消息，加载后内容一致")


def test_history_tool_calls_roundtrip():
    """HistoryStore 工具调用消息序列化"""
    _clean_conversations()
    print("\n" + "=" * 50)
    print("测试 9: HistoryStore 工具调用消息往返")
    store = HistoryStore(root=PROJECT_ROOT)
    store.new_session()

    msgs = [
        Message(role="user", content="3+5=?"),
        Message(
            role="assistant", content="",
            tool_calls=[{
                "id": "call_x", "type": "function",
                "function": {"name": "add", "arguments": '{"a":3,"b":5}'},
            }],
        ),
        Message(role="tool", content="8", tool_call_id="call_x"),
        Message(role="assistant", content="答案是 8"),
    ]
    store.save(msgs)

    loaded = store.load(store._current)
    assert len(loaded) == 4
    assert loaded[1].tool_calls is not None
    assert loaded[1].tool_calls[0]["function"]["name"] == "add"
    assert loaded[2].tool_call_id == "call_x"
    assert "8" in loaded[3].content
    print("  ✅ 通过：tool_calls 和 tool_call_id 序列化/反序列化正确")


def test_agent_with_history_store():
    """Agent 带 HistoryStore，交互后持久化"""
    _clean_conversations()
    print("\n" + "=" * 50)
    print("测试 10: Agent 带 HistoryStore 持久化")
    store = HistoryStore(root=PROJECT_ROOT)
    store.new_session()

    brain = MockBrain([
        Message(role="assistant", content="我叫智序者。"),
    ])
    tools = build_tools()
    recorder = Recorder(root=PROJECT_ROOT)

    agent = Agent(brain=brain, tools=tools, recorder=recorder, history_store=store)
    assert len(agent.history) == 0

    response = agent.run("你是谁？")
    assert "智序者" in response
    assert len(agent.history) == 2  # 内存有 2 条

    # 从磁盘验证
    loaded = store.load(store._current)
    assert len(loaded) == 2
    assert loaded[0].role == "user"
    assert loaded[1].role == "assistant"
    print("  ✅ 通过：Agent 交互后历史正确写入磁盘")


def test_agent_history_restore():
    """Agent 从 HistoryStore 恢复历史"""
    _clean_conversations()
    print("\n" + "=" * 50)
    print("测试 11: Agent 恢复上次会话")
    store = HistoryStore(root=PROJECT_ROOT)
    store.new_session()

    # 模拟上次会话留下 2 条消息
    store.save([
        Message(role="user", content="上一次的问题"),
        Message(role="assistant", content="上一次的回答"),
    ])

    # 新建 Agent 应自动恢复
    brain = MockBrain([])
    tools = build_tools()
    recorder = Recorder(root=PROJECT_ROOT)

    agent = Agent(brain=brain, tools=tools, recorder=recorder, history_store=store)
    assert len(agent.history) == 2
    assert agent.history[0].content == "上一次的问题"
    assert agent.history[1].content == "上一次的回答"
    print("  ✅ 通过：Agent 启动自动恢复上次会话历史")


# ═══════════════════════════════════════════
# 运行所有测试
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║   智序者 ReAct 重构——本地验证            ║")
    print("╚══════════════════════════════════════════╝\n")

    all_pass = True
    tests = [
        test_react_loop_no_tools,
        test_react_loop_with_tool,
        test_react_loop_multi_tool,
        test_agent_normal_mode,
        test_agent_tool_mode,
        test_task_runner,
        test_task_runner_plan_fallback,
        test_history_save_load,
        test_history_tool_calls_roundtrip,
        test_agent_with_history_store,
        test_agent_history_restore,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            all_pass = False

    print("\n" + "=" * 50)
    if all_pass:
        print("🎉 全部测试通过！重构逻辑正确。")
    else:
        print("⚠️  存在失败用例，请检查。")
