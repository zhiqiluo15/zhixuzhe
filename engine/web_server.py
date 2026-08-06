"""智序者 Web Server —— 零依赖 HTTP 后端

提供 REST API + SSE 流式推送，桥接 Agent 到浏览器。

API:
  GET  /           → 前端 UI
  GET  /status     → 服务状态（{ready: bool, error?: str}）
  POST /setup      → 设置 API Key（{key: "sk-xxx"}）
  GET  /skills     → 技能列表 JSON
  POST /chat       → SSE 流式聊天
  POST /task       → SSE 流式任务
  POST /confirm     → HITL 确认响应
  POST /reset      → 重置对话
"""

import json
import os
import sys
import threading
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"

# ── 全局状态 ──

_agent = None
_agent_error: str | None = None  # 初始化失败时的错误信息
_agent_lock = threading.Lock()

# ── HITL 确认状态 ──
_pending_confirms: dict[str, dict] = {}  # confirm_id → {"event": threading.Event, "result": bool}


def _try_init_agent():
    """尝试初始化 Agent。成功返回 Agent，失败设置 _agent_error 并返回 None。"""
    global _agent, _agent_error

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

    from engine.factory import create_agent

    try:
        _agent = create_agent(ROOT)
    except ValueError as e:
        _agent_error = str(e)
        return None

    _agent_error = None
    return _agent


def get_agent():
    """懒初始化 Agent（线程安全）。无 API Key 时返回 None。"""
    global _agent, _agent_error
    if _agent is not None:
        return _agent
    if _agent_error is not None:
        return None  # 已知失败，不重试
    with _agent_lock:
        if _agent is not None:
            return _agent
        if _agent_error is not None:
            return None
        return _try_init_agent()


def reset_agent():
    """重置 Agent 状态（API Key 设置后调用）"""
    global _agent, _agent_error
    with _agent_lock:
        _agent = None
        _agent_error = None


def get_agent_status() -> dict:
    """返回 Agent 状态信息"""
    agent = get_agent()
    if agent is not None:
        return {"ready": True}
    return {"ready": False, "error": _agent_error or "未初始化"}


def _make_web_confirm_callback(sse_write):
    """创建 Web 端 HITL 确认回调。

    通过 SSE 发送 confirm_request 事件给前端，用 threading.Event 等待用户响应。
    60 秒超时未响应则自动拒绝。
    """
    def confirm_callback(tool_name: str, args: dict) -> bool:
        confirm_id = str(uuid.uuid4())
        event = threading.Event()
        _pending_confirms[confirm_id] = {"event": event, "result": False}
        sse_write("confirm_request", {
            "id": confirm_id,
            "tool_name": tool_name,
            "args": args,
        })
        if event.wait(timeout=60):
            result = _pending_confirms.pop(confirm_id, {}).get("result", False)
            return result
        else:
            _pending_confirms.pop(confirm_id, None)
            return False

    return confirm_callback


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

    def _check_agent(self) -> bool:
        """检查 Agent 是否就绪，未就绪则返回 503 错误"""
        status = get_agent_status()
        if status["ready"]:
            return True
        self._error(503, status.get("error", "服务未就绪"))
        return False

    # ── Routing ──

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_page()
        elif self.path == "/status":
            self._serve_status()
        elif self.path == "/skills":
            if self._check_agent():
                self._serve_skills()
        else:
            self._error(404, "Not Found")

    def do_POST(self):
        if self.path == "/setup":
            self._handle_setup()
        elif self.path == "/chat":
            if self._check_agent():
                self._handle_chat()
        elif self.path == "/task":
            if self._check_agent():
                self._handle_task()
        elif self.path == "/confirm":
            self._handle_confirm()
        elif self.path == "/reset":
            if self._check_agent():
                self._handle_reset()
        else:
            self._error(404, "Not Found")

    # ── 状态 ──

    def _serve_status(self):
        self._ok()
        self.wfile.write(json.dumps(get_agent_status(), ensure_ascii=False).encode())

    # ── API Key 设置 ──

    def _handle_setup(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            api_key = body.get("key", "").strip()
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        if not api_key:
            self._error(400, "API Key 不能为空")
            return

        # 写入 .env 文件
        env_path = ROOT / ".env"
        existing = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()

        existing["DEEPSEEK_API_KEY"] = api_key
        lines = [f"{k}={v}" for k, v in existing.items()]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # 重新加载配置（让新的 API Key 生效）
        os.environ["DEEPSEEK_API_KEY"] = api_key

        # 重置 Agent 状态
        reset_agent()

        # 尝试初始化
        agent = get_agent()
        if agent is not None:
            self._ok()
            self.wfile.write(json.dumps({
                "status": "ok",
                "tools": agent.tool_count,
                "skills": agent.skill_count,
            }, ensure_ascii=False).encode())
        else:
            self._error(500, _agent_error or "初始化失败")

    # ── HITL 确认 ──

    def _handle_confirm(self):
        """处理前端 HITL 确认响应"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            confirm_id = body.get("id", "")
            approved = body.get("approved", False)
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        pending = _pending_confirms.get(confirm_id)
        if pending is None:
            self._error(404, "确认请求已过期或不存在")
            return

        pending["result"] = approved
        pending["event"].set()

        self._ok()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

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
                for s in agent.skill_registry.list_all()
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
        self.send_header("X-Accel-Buffering", "no")
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

        confirm_callback = _make_web_confirm_callback(sse_write)

        try:
            response = agent.run(
                message,
                stream_callback=stream_callback,
                confirm_callback=confirm_callback,
            )
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
            sse_write("task_start", {"goal": goal})

            def verbose_callback(msg: str) -> None:
                sse_write("task_step", {"content": msg})

            confirm_callback = _make_web_confirm_callback(sse_write)

            response = agent.task_runner.run(
                goal, verbose=True,
                verbose_callback=verbose_callback,
                confirm_callback=confirm_callback,
            )

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

    # 尝试预初始化
    agent = get_agent()
    if agent is not None:
        print(f"  Agent 就绪（{agent.tool_count} 个工具，{agent.skill_count} 个技能）")
    else:
        print(f"  ⚠️  Agent 未就绪: {_agent_error}")
        print(f"  打开浏览器后将引导设置 API Key")

    print(f"\n  打开浏览器访问: http://localhost:{port}\n")

    server = ThreadingHTTPServer(("127.0.0.1", port), ZhixuzheHandler)
    print(f"  服务运行在 http://localhost:{port}（仅本机访问）")
    print(f"  按 Ctrl+C 停止\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止。")
        server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    main(port)
