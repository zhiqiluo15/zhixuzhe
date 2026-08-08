"""验证分层记忆检索 → system prompt 注入 —— 端到端模拟

流程：
1. 在临时目录中写入测试日记和经验
2. 创建 Agent（含 MemoryManager），用 SpyBrain 捕获 system prompt
3. 发起相关查询，验证 system prompt 中是否出现检索到的记忆
4. 再发起无关查询，验证无记忆时不注入
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.brain.base import Brain, Message
from engine.tools.registry import ToolRegistry, Tool
from engine.core.recorder import Recorder
from engine.core.loop import Agent
from engine.core.memory_reader import MemoryReader, _parse_diary_entries
from engine.core.memory_manager import MemoryManager


# ── 模拟大脑：记录每次 think 收到的 system prompt ──

class SpyBrain(Brain):
    """间谍大脑：不联网，记录最后一次 think 时的 messages"""

    def __init__(self, answer: str = "收到。"):
        self.answer = answer
        self.last_messages: list[Message] = []
        self.calls: list[dict] = []

    def think(
        self, messages: list[Message], tools: list[dict] | None = None
    ) -> Message:
        self.last_messages = messages
        self.calls.append({
            "msg_count": len(messages),
            "system_content": messages[0].content if messages else "",
        })
        return Message(role="assistant", content=self.answer)


# ── 准备：写入测试日记和经验（使用临时目录隔离） ──

def setup_memories(root: Path):
    """在指定 root 下写入测试日记和经验"""
    # 创建 memory 目录结构
    (root / "memory" / "diary").mkdir(parents=True, exist_ok=True)
    (root / "memory" / "experience").mkdir(parents=True, exist_ok=True)

    recorder = Recorder(root=root)

    # 模拟几次真实交互的日记
    recorder.record("帮我检测这台电脑的硬件", "已检测：CPU Intel 14代，GPU RTX 5060 8GB，内存 16GB。")
    recorder.record("QLoRA 微调需要什么条件？", "QLoRA 需要至少 8GB 显存，你的 RTX 5060 刚好满足。推荐 4-bit 量化。")
    recorder.record("今天天气怎么样？", "抱歉，我还没有接入天气 API，无法查询。")
    recorder.record("什么是 Python 装饰器？", "装饰器是一种修改函数行为的语法糖…")

    # 记录一次任务经验
    recorder.record_task(
        goal="全面检测硬件并判断 QLoRA 微调条件",
        plan=["检测硬件", "验证 GPU 算力", "综合评估"],
        step_results=[
            "CPU: Intel 14代, GPU: RTX 5060 8GB",
            "矩阵乘加速 13.4x，CUDA 可用",
            "8GB 显存满足 QLoRA 最低要求，推荐 3B-4B 模型",
        ],
        final_answer="你的 RTX 5060 8GB 刚好进入 QLoRA 舒适区，推荐从 Qwen2.5-3B 开始。",
        plan_source="skill:hardware_check",
    )

    # 写一条经验
    recorder.record_experience(
        scene="在 RTX 5060 上尝试 QLoRA 微调 7B 模型时遇到 OOM",
        lesson="必须开启 gradient checkpointing 并将 batch size 设为 1，显存刚好够用但非常紧张。建议回退到 3B 模型。",
    )

    print(f"[setup] 已写入 4 条日记 + 1 条任务 + 1 条经验 (root={root})\n")


# ── 测试 1：相关查询 → 应注入记忆 ──

def test_memory_injection_for_relevant_query(root: Path):
    print("=" * 60)
    print("测试 A: 相关查询（硬件/QLoRA）→ 应注入记忆")
    print("=" * 60)

    brain = SpyBrain("好的，我查一下。")
    tools = ToolRegistry()
    tools.register(Tool(name="dummy", description="占位", func=lambda: ""))
    recorder = Recorder(root=root)

    reader = MemoryReader(root=root)
    manager = MemoryManager(reader)

    agent = Agent(
        brain=brain, tools=tools, recorder=recorder,
        memory_manager=manager,
    )

    response = agent.run("我的显卡能不能跑 QLoRA？")

    # 检查 system prompt 中是否包含记忆
    system_content = brain.calls[0]["system_content"]
    has_memory_block = "【相关历史经验】" in system_content
    has_rtx = "RTX 5060" in system_content
    has_qlora = "QLoRA" in system_content

    print(f"  是否包含 【相关历史经验】 区块: {'✅ 是' if has_memory_block else '❌ 否'}")
    print(f"  是否提到 RTX 5060:               {'✅ 是' if has_rtx else '❌ 否'}")
    print(f"  是否提到 QLoRA:                  {'✅ 是' if has_qlora else '❌ 否'}")

    if has_memory_block:
        # 提取记忆区块
        idx = system_content.index("【相关历史经验】")
        snippet = system_content[idx:idx + 500]
        print(f"\n  记忆区块内容预览:\n  ---\n{snippet}\n  ---")
    else:
        print("\n  System prompt 中无记忆区块（这可能是 bug）")

    assert has_memory_block, "相关查询应触发记忆检索并注入 system prompt"
    assert has_qlora, "检索到的记忆中应包含 QLoRA 相关信息"
    print("\n  ✅ 测试 A 通过：相关查询正确注入了历史记忆\n")


# ── 测试 2：无关查询 → 不应注入记忆 ──

def test_no_memory_for_irrelevant_query(root: Path):
    print("=" * 60)
    print("测试 B: 无关查询（晚饭）→ 不应注入记忆")
    print("=" * 60)

    brain = SpyBrain("好的。")
    tools = ToolRegistry()
    tools.register(Tool(name="dummy", description="占位", func=lambda: ""))
    recorder = Recorder(root=root)

    reader = MemoryReader(root=root)
    manager = MemoryManager(reader)

    # 先调试：直接看 reader 返回什么
    raw = reader.retrieve("晚上吃草莓蛋糕好吗", 3)
    print(f"  Reader 直接检索到: {len(raw)} 条")

    agent = Agent(
        brain=brain, tools=tools, recorder=recorder,
        memory_manager=manager,
    )

    response = agent.run("晚上吃草莓蛋糕好吗")

    system_content = brain.calls[0]["system_content"]
    has_memory_block = "【相关历史经验】" in system_content

    print(f"  是否包含 【相关历史经验】 区块: {'❌ 否（正确）' if not has_memory_block else '⚠️ 是（不该有）'}")
    print(f"  System prompt 长度: {len(system_content)} 字符")

    assert not has_memory_block, f"无关查询不应触发记忆注入，但检索到了 {len(raw)} 条"
    print("\n  ✅ 测试 B 通过：无关查询未注入记忆\n")


# ── 测试 3：无 MemoryManager → 不注入（向后兼容） ──

def test_no_memory_manager(root: Path):
    print("=" * 60)
    print("测试 C: 无 MemoryManager → 不注入（向后兼容）")
    print("=" * 60)

    brain = SpyBrain("收到。")
    tools = ToolRegistry()
    tools.register(Tool(name="dummy", description="占位", func=lambda: ""))
    recorder = Recorder(root=root)

    agent = Agent(
        brain=brain, tools=tools, recorder=recorder,
        memory_manager=None,  # 不传
    )

    response = agent.run("我的显卡能不能跑 QLoRA？")

    system_content = brain.calls[0]["system_content"]
    has_memory_block = "【相关历史经验】" in system_content

    print(f"  是否包含 【相关历史经验】 区块: {'❌ 否（正确，符合向后兼容）' if not has_memory_block else '⚠️ 是（不该有）'}")
    print(f"  System prompt 长度: {len(system_content)} 字符")

    assert not has_memory_block, "无 MemoryManager 时不应注入"
    print("\n  ✅ 测试 C 通过：不传 memory_manager 时向后兼容\n")


# ── 测试 4：经验检索 ──

def test_experience_retrieval(root: Path):
    print("=" * 60)
    print("测试 D: 经验检索 → 应检索到 record_experience 写入的内容")
    print("=" * 60)

    reader = MemoryReader(root=root)
    results = reader.retrieve_experience("QLoRA OOM", top_k=3)

    has_experience = len(results) > 0
    print(f"  检索到经验条目: {len(results)} 条")
    for r in results:
        print(f"  - score={r['score']}  date={r['date']}")
        print(f"    content: {r['content'][:120]}...")

    assert has_experience, "应能检索到之前写入的经验"
    assert any("OOM" in r["content"] or "batch" in r["content"] for r in results), \
        "经验内容应包含 OOM 或 batch size 相关信息"

    print("\n  ✅ 测试 D 通过：经验检索正常\n")


# ── 测试 5：知识文件解析（无时间戳的 ## 标题）──

def test_parse_knowledge_entries():
    """_parse_diary_entries 应正确解析无时间戳的知识文件格式。

    知识文件格式：# 标题 + 元数据头 + ## 主标题 + ### 子标题（属于 body）
    修复 P0 bug 前，解析器要求 ## 后必须有时间戳，导致知识文件返回 0 条。
    """
    print("=" * 60)
    print("测试 E: 知识文件格式解析（无时间戳 ## 标题）")
    print("=" * 60)

    knowledge_md = """# FastAPI 最佳实践

> 领域：Python
> 学习时间：2026-08-08

---

## 学习报告：FastAPI 核心设计模式

### 1. 依赖注入系统

FastAPI 使用 Depends() 实现依赖注入...

### 2. Pydantic 数据校验

所有请求/响应模型通过 Pydantic 定义...

### 3. 安全中间件

推荐用 OAuth2PasswordBearer 处理认证...
"""

    entries = _parse_diary_entries(knowledge_md)
    print(f"  解析出条目数: {len(entries)}")
    assert len(entries) == 1, f"应解析出 1 条知识条目，实际 {len(entries)} 条"

    entry = entries[0]
    print(f"  title: {entry['title']}")
    assert "学习报告" in entry["title"], "标题应包含学习报告文字"
    assert "FastAPI" in entry["body"], "body 应包含 FastAPI 内容"
    assert "依赖注入" in entry["body"], "body 应包含子标题内容"
    assert "Pydantic" in entry["body"], "### 子标题内容应保留在 body 中"

    print("  ✅ 测试 E 通过：知识文件格式正确解析\n")


def test_parse_diary_entries_with_timestamps():
    """_parse_diary_entries 应继续兼容日记/经验文件的时间戳格式。"""
    print("=" * 60)
    print("测试 F: 日记/经验格式兼容（有时间戳 ## 标题）")
    print("=" * 60)

    diary_md = """# 智序者日记 - 2026-08-08

## 10:30:15

**问**：你好
**答**：你好！

---

## [任务] 11:20:33

**目标**：检测硬件
**计划**：...
"""

    entries = _parse_diary_entries(diary_md)
    print(f"  解析出条目数: {len(entries)}")
    assert len(entries) == 2, f"应解析出 2 条，实际 {len(entries)} 条"
    assert entries[0]["title"] == "10:30:15", "第一条标题应为时间戳"
    assert entries[1]["title"] == "[任务] 11:20:33", "第二条标题应包含[任务]标记"

    print("  ✅ 测试 F 通过：日记格式向后兼容\n")


def test_knowledge_retrieval_from_file(root: Path):
    """写入知识文件后，retrieve_knowledge 应能检索到内容。"""
    print("=" * 60)
    print("测试 G: 知识文件端到端检索")
    print("=" * 60)

    # 创建知识目录和文件
    knowledge_dir = root / "memory" / "knowledge" / "languages" / "Python"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    knowledge_file = knowledge_dir / "FastAPI.md"
    knowledge_file.write_text("""# FastAPI

> 领域：Python
> 学习时间：2026-08-08

---

## 学习报告：FastAPI 异步编程最佳实践

### 核心概念
FastAPI 基于 Starlette 构建，原生支持 async/await。
使用 Depends() 进行依赖注入，Pydantic 做数据校验。

### 性能要点
异步路由函数应使用 async def，避免阻塞 IO 操作。
数据库操作推荐使用 SQLAlchemy 2.0 的 async 引擎。
""", encoding="utf-8")

    reader = MemoryReader(root=root)
    results = reader.retrieve_knowledge("FastAPI 异步 async Pydantic", top_k=3)

    print(f"  检索到知识条目: {len(results)} 条")
    for r in results:
        print(f"  - score={r['score']} date={r['date']}")
        print(f"    content: {r['content'][:100]}...")

    assert len(results) > 0, "应能检索到刚写入的知识文件"
    assert any("FastAPI" in r["content"] for r in results), "检索结果应包含 FastAPI"
    assert any("Pydantic" in r["content"] for r in results), "检索结果应包含 Pydantic"

    print("  ✅ 测试 G 通过：知识文件端到端检索正常\n")


# ── 运行 ──

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║   分层记忆 —— 端到端注入验证              ║")
    print("╚══════════════════════════════════════════╝\n")

    all_pass = True

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        setup_memories(root)

        tests = [
            ("A: 相关查询注入", test_memory_injection_for_relevant_query),
            ("B: 无关查询不注入", test_no_memory_for_irrelevant_query),
            ("C: 向后兼容（无 Manager）", test_no_memory_manager),
            ("D: 经验检索", test_experience_retrieval),
        ]

        for name, test_func in tests:
            try:
                test_func(root)
            except Exception as e:
                print(f"  ❌ {name} 失败: {e}")
                import traceback
                traceback.print_exc()
                all_pass = False

    print("=" * 60)
    if all_pass:
        print("🎉 全部 4 项验证通过！")
        print("  相关查询 → 记忆注入 system prompt ✅")
        print("  无关查询 → 不注入 ✅")
        print("  无 MemoryManager → 向后兼容 ✅")
        print("  经验检索 → 正常 ✅")
    else:
        print("⚠️  存在失败项")
