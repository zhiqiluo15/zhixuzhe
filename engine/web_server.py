"""智序者 Web Server —— 零依赖 HTTP 后端

提供 REST API + SSE 流式推送，桥接 Agent 到浏览器。

API:
  GET  /           → 前端 UI
  GET  /skills     → 技能列表 JSON
  POST /chat       → SSE 流式聊天
  POST /task       → SSE 流式任务
  POST /reset      → 重置对话
"""

import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"

# ── 全局 Agent 实例（单例，所有请求共享） ──

_agent = None
_agent_lock = threading.Lock()


def get_agent():
    """懒初始化 Agent（线程安全）"""
    global _agent
    if _agent is not None:
        return _agent
    with _agent_lock:
        if _agent is not None:
            return _agent

        sys.path.insert(0, str(ROOT))

        from engine.config import config
        from engine.log import init_logging

        init_logging(
            log_dir=config.logging.dir,
            level=config.logging.level,
            fmt=config.logging.format,
            max_bytes=config.logging.file_max_bytes,
            backup_count=config.logging.file_backup_count,
        )

        from engine.brain.deepseek_api import DeepSeekAPIBrain
        from engine.tools.registry import ToolRegistry, Tool
        from engine.tools.detect_host import detect_host
        from engine.tools.verify_gpu import verify_gpu
        from engine.tools.shell import run_shell
        from engine.tools.file_io import read_file, write_file
        from engine.tools.web_fetch import web_fetch
        from engine.skills.registry import SkillRegistry
        from engine.skills.hardware_check.skill import HardwareCheckSkill
        from engine.core.loop import Agent
        from engine.core.recorder import Recorder
        from engine.core.history import HistoryStore
        from engine.core.memory_reader import MemoryReader
        from engine.core.memory_manager import MemoryManager

        brain = DeepSeekAPIBrain(
            model=config.model.model,
            base_url=config.model.base_url,
        )

        tools = ToolRegistry()
        tools.register(Tool(name="detect_host", description="检测宿主机信息", func=detect_host))
        tools.register(Tool(name="verify_gpu", description="验证 GPU 算力", func=verify_gpu))
        tools.register(Tool(
            name="run_shell", description="执行 PowerShell 命令",
            func=run_shell,
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell 命令"},
                    "timeout": {"type": "integer", "description": "超时秒数"},
                },
                "required": ["command"],
            },
            max_retries=config.tools.shell.max_retries,
        ))
        tools.register(Tool(
            name="read_file", description="读取项目内文件",
            func=read_file,
            parameters={"type": "object", "properties": {"filepath": {"type": "string"}}, "required": ["filepath"]},
        ))
        tools.register(Tool(
            name="write_file", description="写入项目内文件",
            func=write_file,
            parameters={"type": "object", "properties": {"filepath": {"type": "string"}, "content": {"type": "string"}}, "required": ["filepath", "content"]},
        ))
        tools.register(Tool(
            name="web_fetch", description="获取网页内容",
            func=web_fetch,
            parameters={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        ))

        skills = SkillRegistry()
        skills.register(HardwareCheckSkill())

        recorder = Recorder(root=ROOT)
        history_store = HistoryStore(root=ROOT)
        memory_reader = MemoryReader(root=ROOT)
        memory_manager = MemoryManager(memory_reader)

        confirm_tools = set(config.agent.confirm_tools)

        _agent = Agent(
            brain=brain, tools=tools,
            recorder=recorder, history_store=history_store,
            skill_registry=skills,
            memory_manager=memory_manager,
            confirm_tools=confirm_tools,
        )
        return _agent


# ── 读取前端 HTML ──

_PAGE = None


def _load_page() -> str:
    global _PAGE
    if _PAGE is not None:
        return _PAGE
    html_path = WEB_DIR / "index.html"
    if html_path.exists():
        _PAGE = html_path.read_text(encoding="utf-8")
    else:
        _PAGE = "<h1>index.html 未找到</h1>"
    return _PAGE


# ── HTTP Handler ──

class ZhixuzheHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        """抑制默认日志（用我们的 logger）"""
        pass

    # ── CORS + 公共头 ──

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _ok(self, content_type="application/json"):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.end_headers()

    def _error(self, code, msg):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode())

    # ── Routing ──

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_page()
        elif self.path == "/skills":
            self._serve_skills()
        else:
            self._error(404, "Not Found")

    def do_POST(self):
        if self.path == "/chat":
            self._handle_chat()
        elif self.path == "/task":
            self._handle_task()
        elif self.path == "/reset":
            self._handle_reset()
        else:
            self._error(404, "Not Found")

    # ── 页面 ──

    def _serve_page(self):
        self._ok("text/html")
        self.wfile.write(_load_page().encode())

    # ── 技能列表 ──

    def _serve_skills(self):
        agent = get_agent()
        if agent.skill_registry:
            skills = [
                {"name": s.name, "description": s.description, "triggers": s.triggers}
                for s in agent.skill_registry._skills.values()
            ]
        else:
            skills = []
        self._ok()
        self.wfile.write(json.dumps({"skills": skills}, ensure_ascii=False).encode())

    # ── SSE 流式聊天 ──

    def _handle_chat(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            message = body.get("message", "").strip()
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        if not message:
            self._error(400, "消息不能为空")
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")  # 禁用 nginx 缓冲
        self.end_headers()

        agent = get_agent()

        def sse_write(event_type: str, data: dict) -> None:
            payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
            try:
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def stream_callback(chunk: str) -> None:
            sse_write("text", {"content": chunk})

        try:
            response = agent.run(message, stream_callback=stream_callback)
            sse_write("done", {"content": response})
        except Exception as e:
            sse_write("error", {"content": str(e)})

    # ── 任务模式 ──

    def _handle_task(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            goal = body.get("goal", "").strip()
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        if not goal:
            self._error(400, "目标不能为空")
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        agent = get_agent()

        def sse_write(event_type: str, data: dict) -> None:
            payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
            try:
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        try:
            # 任务模式：先通知开始，执行期间逐步推送步骤，最后推送结论
            sse_write("task_start", {"goal": goal})

            import io
            old_stdout = sys.stdout
            buf = io.StringIO()

            # 自定义 verbose 输出捕获
            class _StepCapture:
                def __init__(self, sse_fn):
                    self.sse_fn = sse_fn
                    self.current_step = ""

                def write(self, s):
                    self.current_step += s
                    if "\n" in self.current_step:
                        lines = self.current_step.split("\n")
                        for line in lines[:-1]:
                            stripped = line.strip()
                            if stripped:
                                self.sse_fn("task_step", {"content": stripped})
                        self.current_step = lines[-1]

                def flush(self):
                    if self.current_step.strip():
                        self.sse_fn("task_step", {"content": self.current_step.strip()})
                        self.current_step = ""

            capture = _StepCapture(sse_write)
            sys.stdout = capture

            try:
                response = agent.task_runner.run(
                    goal,
                    verbose=True,
                    confirm_callback=None,  # Web 模式不交互确认
                )
            finally:
                sys.stdout = old_stdout

            sse_write("task_done", {"content": response})
        except Exception as e:
            sse_write("error", {"content": str(e)})

    # ── 重置 ──

    def _handle_reset(self):
        agent = get_agent()
        agent.history.clear()
        if agent.history_store:
            agent.history_store.new_session()
        self._ok()
        self.wfile.write(json.dumps({"status": "ok"}).encode())


# ── 启动 ──

def main(port: int = 8080):
    print(f"\n  智序者 Web UI 启动中...")
    print(f"  打开浏览器访问: http://localhost:{port}\n")

    # 预初始化 Agent
    agent = get_agent()
    print(f"  Agent 就绪（{len(agent.tools._tools)} 个工具，{len(agent.skill_registry)} 个技能）\n")

    server = HTTPServer(("0.0.0.0", port), ZhixuzheHandler)
    print(f"  服务运行在 http://localhost:{port}")
    print(f"  按 Ctrl+C 停止\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止。")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    main(port)
