# 智序者 v1.1 修复计划：11 项问题全面修复

## Context

2026-08-06 全面体检发现智序者存在 11 项问题，涉及安全漏洞（P0-1）、功能 bug（P0-2）、容错缺陷（P1-3）、规范违规（P1-4）、以及代码质量（P2-6/7, P3-8/9/10/11）。本次修复将一并解决。

## 修复概览

| 优先级 | 编号 | 问题 | 文件 |
|--------|------|------|------|
| P0 | 1 | Web 端 HITL 绕过 | loop.py, web_server.py, index.html |
| P0 | 2 | write_file append 失效 | file_io.py |
| P1 | 3 | think() 4xx 重试 bug | deepseek_api.py |
| P1 | 4 | CHANGELOG 补记 | CHANGELOG.md |
| P2 | 6 | Agent 组装逻辑重复 | 新建 factory.py, __main__.py, web_server.py |
| P2 | 7 | stdout 劫持 hack 复活 | task.py, web_server.py |
| P3 | 8 | 经验写入无去重 | recorder.py |
| P3 | 9 | think_stream 无重试 | deepseek_api.py |
| P3 | 10 | 测试用 return 而非 assert | test_memory.py |
| P3 | 11 | 多处访问私有属性 | registry.py, loop.py 等 |

## 执行顺序（依赖关系）

```
Phase 1: 基础修复（P3-11, P0-2, P1-3, P3-9, P3-10）—— 互不依赖，可并行
Phase 2: 工厂抽取（P2-6）—— 依赖 P3-11
Phase 3: TaskRunner 回调（P2-7）—— 依赖 P2-6
Phase 4: Web HITL（P0-1）—— 依赖 P2-6, P2-7
Phase 5: 经验去重（P3-8）—— 独立
Phase 6: CHANGELOG（P1-4）—— 依赖以上全部
```

---

## Phase 1: 基础修复（5 项独立）

### Step 1.1 — P3-11: 添加公共 API 替换私有属性访问

**`engine/tools/registry.py`** — 在 `ToolRegistry` 类中添加：
```python
def __len__(self) -> int:
    return len(self._tools)

def names(self) -> list[str]:
    return list(self._tools.keys())

def __contains__(self, name: str) -> bool:
    return name in self._tools

def __iter__(self):
    return iter(self._tools)
```

**`engine/skills/registry.py`** — 在 `SkillRegistry` 类中添加：
```python
def names(self) -> list[str]:
    return list(self._skills.keys())

def list_all(self) -> list:
    return list(self._skills.values())
```

**`engine/core/history.py`** — 在 `HistoryStore` 类中添加：
```python
@property
def current_session_name(self) -> str | None:
    return self._current.name if self._current else None

def set_current_session(self, path: Path) -> None:
    self._current = path
```

**`engine/core/loop.py`** — 在 `Agent` 类中添加：
```python
@property
def tool_count(self) -> int:
    return len(self.tools)

@property
def skill_count(self) -> int:
    return len(self.skill_registry) if self.skill_registry else 0
```

**替换所有私有属性调用**（批量替换）：

| 文件 | 旧代码 | 新代码 |
|------|--------|--------|
| `__main__.py:134` | `len(tools._tools)` | `len(tools)` |
| `__main__.py:134` | `', '.join(tools._tools)` | `', '.join(tools.names())` |
| `task.py:144` | `self.tools._tools.keys()` | `self.tools.names()` |
| `web_server.py:289` | `len(agent.tools._tools)` | `agent.tool_count` |
| `web_server.py:308` | `agent.skill_registry._skills.values()` | `agent.skill_registry.list_all()` |
| `web_server.py:446` | `len(agent.tools._tools)` | `agent.tool_count` |
| `loop.py:71` | `history_store._current = latest` | `history_store.set_current_session(latest)` |
| `loop.py:171` | `self.history_store._current.name` | `self.history_store.current_session_name` |

### Step 1.2 — P0-2: write_file append 模式修复

**`engine/tools/file_io.py`** 第 83-87 行：

```python
# 旧代码（mode 计算了但未使用，永远覆盖）
path.parent.mkdir(parents=True, exist_ok=True)
mode = "a" if append else "w"
path.write_text(content, encoding="utf-8")

# 新代码
path.parent.mkdir(parents=True, exist_ok=True)
mode = "a" if append else "w"
with path.open(mode, encoding="utf-8") as f:
    f.write(content)
```

### Step 1.3 — P1-3: think() 4xx 不重试修复

**`engine/brain/deepseek_api.py`** `think()` 方法第 91-99 行：

```python
# 旧代码（raise_for_status → 被外层 except 捕获 → 继续重试）
if resp.status_code == 429 or resp.status_code >= 500:
    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
else:
    resp.raise_for_status()  # ← 被 except RequestException 捕获，继续循环

# 新代码（直接 return，不抛异常）
if resp.status_code == 429 or resp.status_code >= 500:
    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
else:
    logger.error(f"API 不可重试错误 HTTP {resp.status_code}: {resp.text[:200]}")
    return Message(
        role="assistant",
        content=f"[API 错误 HTTP {resp.status_code}] {resp.text[:200]}",
    )
```

### Step 1.4 — P3-9: think_stream 添加重试

**`engine/brain/deepseek_api.py`** `think_stream()` 方法：

将 `requests.post()` 调用（第 140-153 行）包裹在 `for attempt in range(config.model.max_retries)` 循环中：
- 429/5xx/网络错误 → 指数退避后重试（与 `think()` 一致）
- 4xx 非 429 → 立即 yield 错误返回
- 成功 → break 进入流式迭代
- 全败 → yield 错误返回

### Step 1.5 — P3-10: 测试 assert 修复

**`engine/tests/test_memory.py`**：删除 4 个测试函数末尾的 `return True` 语句（第 126, 163, 193, 217 行）。

---

## Phase 2: Agent 工厂抽取

### Step 2.1 — P2-6: 新建 `engine/factory.py`

创建 `create_agent(project_root: Path) -> Agent` 函数，包含：
- 大脑初始化（`DeepSeekAPIBrain`，可能抛出 `ValueError`）
- 6 个工具注册
- 1 个技能注册（`HardwareCheckSkill`）
- 记忆组件创建（Recorder / HistoryStore / MemoryReader / MemoryManager）
- Agent 组装返回

### Step 2.2 — 重构 `engine/core/__main__.py`

将第 26-168 行（大脑、手脚、技能、记忆、组装）替换为：
```python
from engine.factory import create_agent
try:
    agent = create_agent(project_root)
except ValueError as e:
    logger.error(str(e))
    sys.exit(1)
logger.info(f"已注册 {agent.tool_count} 个工具: {', '.join(agent.tools.names())}")
logger.info(f"已注册 {agent.skill_count} 个技能")
```

### Step 2.3 — 重构 `engine/web_server.py` `_try_init_agent()`

将第 37-123 行（组装逻辑）替换为：
```python
from engine.factory import create_agent
try:
    _agent = create_agent(ROOT)
except ValueError as e:
    _agent_error = str(e)
    return None
```

---

## Phase 3: TaskRunner 原生回调

### Step 3.1 — P2-7: 添加 `verbose_callback` 参数

**`engine/core/task.py`**：
- `run()` 方法签名新增 `verbose_callback: Callable[[str], None] | None = None`
- 添加 `_vprint(msg)` 内部辅助函数：有 `verbose_callback` 时调用回调，否则回退 `print()`
- 替换 `run()` 内所有 `print(...)` 为 `_vprint(...)`

**`engine/web_server.py`** `_handle_task()`：
- 删除 `_StepCapture` 类 + `sys.stdout` 劫持（第 390-421 行）
- 替换为直接传入 `verbose_callback`：
```python
def verbose_callback(msg):
    sse_write("task_step", {"content": msg})

response = agent.task_runner.run(
    goal, verbose=True,
    verbose_callback=verbose_callback,
    confirm_callback=confirm_callback,
)
```

---

## Phase 4: Web HITL 安全修复

### Step 4.1 — P0-1: `Agent.run()` 显式 confirm_callback 参数

**`engine/core/loop.py`** `run()` 方法：

- 签名新增 `confirm_callback: ConfirmCallback | None = None`
- 优先级：显式传入 > CLI 默认 `_hitl_confirm` > None
- 向后兼容：不传时行为与旧代码完全一致

### Step 4.2 — P0-1: Web Server HITL 基础设施

**`engine/web_server.py`**：

- 添加全局 `_pending_confirms: dict[str, dict]` + `uuid` / `threading` 导入
- 将 `HTTPServer` 改为 `ThreadingHTTPServer`（支持 SSE 流期间并发处理 `/confirm` 请求）
- 新增 `/confirm` POST 端点：接收 `{id, approved}`，设置对应 Event
- 新增模块级 `_make_web_confirm_callback(sse_write)` 工厂函数：
  - 生成 confirm_id，创建 `threading.Event`
  - 通过 SSE 发送 `confirm_request` 事件给前端
  - 等待 60 秒，超时则拒绝
- `_handle_chat` 和 `_handle_task` 都使用此回调

### Step 4.3 — P0-1: 前端确认对话框

**`engine/web/index.html`**：

- 添加 CSS 样式：确认覆盖层（深色背景、毛玻璃、红色边框卡片）
- 添加 HTML：确认对话框（工具名 + 参数展示 + 拒绝/允许按钮）
- 添加 JS：`showConfirmDialog(id, toolName, args)` + `respondConfirm(approved)`
- SSE 事件处理新增 `confirm_request` 分支

---

## Phase 5: 经验写入去重

### Step 5.1 — P3-8: `_write_experience` 去重

**`engine/core/recorder.py`** `_write_experience()` 方法：

写入前检查当日经验文件中是否已存在相同的**场景**+**教训**组合，存在则跳过。

---

## Phase 6: CHANGELOG 更新

### Step 6.1 — P1-4: CHANGELOG 补记

**`CHANGELOG.md`** 末尾追加两个新章节：

1. **Web Server 模块**：记录 web_server.py、index.html、启动脚本的架构与设计决策
2. **v1.1 修复**：逐条记录 11 项问题修复（问题、原因、方案、影响）

---

## 验证计划

| 序号 | 验证项 | 方法 |
|------|--------|------|
| 1 | 单元测试 | `python -m pytest engine/tests/ -v`，期望 20/20 通过，无 warning |
| 2 | CLI 启动 | `python -m engine.core`，验证工具/技能数量正确，HITL 正常 |
| 3 | Web 启动 | `python engine/web_server.py`，验证 API Key 设置、流式聊天、任务模式 |
| 4 | append 修复 | 手动调用 write_file 两次（覆盖 + 追加），验证文件内容 |
| 5 | 4xx 不重试 | 临时用无效 API Key，验证立即返回错误（不重试 3 次） |
| 6 | 流式重试 | 模拟网络断开，验证退避重试 |
| 7 | 经验去重 | 调用 record_experience 两次相同内容，验证只写一次 |
| 8 | Web HITL | 发消息触发 run_shell，验证浏览器弹出确认框，yes/no 行为正确 |
| 9 | 工厂一致性 | 验证 CLI 和 Web 使用同一工厂，工具/技能数量一致 |

## 影响范围

- **向后兼容**：所有公开 API 仅新增可选参数，不改变默认行为
- **安全**：Web HITL 修复消除 CSRF → RCE 攻击链
- **代码量**：净减少 ~80 行（消除 90 行重复 + 40 行 stdout hack，新增 ~150 行工厂 + ~50 行 HITL 基础设施）