"""智序者 Web Server —— 零依赖 HTTP 后端

提供 REST API + SSE 流式推送，桥接 Agent 到浏览器。

API:
  GET  /           → 前端 UI
  GET  /status     → 服务状态（{ready: bool, error?: str}）
  POST /setup      → 设置 API Key（{key: "sk-xxx"}）
  GET  /skills     → 技能列表 JSON
  POST /chat       → SSE 流式聊天
  POST /task       → SSE 流式任务
  POST /chain      → SSE 流式技能链（{goal, skills: [...]}）
  POST /confirm     → HITL 确认响应
  POST /reset      → 重置对话

安全设计（P0 三件套）：
  1. CORS 收紧：仅允许本地源 http://127.0.0.1:<port> / http://localhost:<port>，杜绝跨域读取
  2. Origin/Referer 校验：所有 POST 与 OPTIONS 预检强制校验来源，挡盲发请求
  3. Session 绑定：GET / 下发 HttpOnly+SameSite=Strict cookie，/confirm 校验 session 与 confirm_id 一致，防跨会话代答
"""

import json
import logging
import os
import secrets
import sys
import threading
import uuid
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger("zhixuzhe.web_server")

# 项目根
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"

# ── 全局状态 ──

_agent = None
_agent_error: str | None = None  # 初始化失败时的错误信息
_agent_lock = threading.Lock()

# ── HITL 确认状态 ──
_pending_confirms: dict[str, dict] = {}  # confirm_id → {"event", "result", "session_id"}
_pending_confirms_lock = threading.Lock()  # 保护 _pending_confirms 的并发访问


def _try_init_agent():
    """尝试初始化 Agent。成功返回 Agent，失败设置 _agent_error 并返回 None。"""
    global _agent, _agent_error

    sys.path.insert(0, str(ROOT))

    try:
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

        _agent = create_agent(ROOT)
    except ValueError as e:
        _agent_error = str(e)
        return None
    except Exception as e:
        # 任何意外异常都转化为可读错误，不能击穿请求线程
        # （否则连接被掐断，前端 fetch 拒绝 → 显示"网络错误"）
        logger.error(f"Agent 初始化失败（{type(e).__name__}）: {e}")
        _agent_error = f"Agent 初始化失败（{type(e).__name__}）: {e}"
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


def _make_web_confirm_callback(sse_write, session_id: str):
    """创建 Web 端 HITL 确认回调（绑定 session_id）。

    通过 SSE 发送 confirm_request 事件给前端，用 threading.Event 等待用户响应。
    60 秒超时未响应则自动拒绝。confirm_id 与 session_id 绑定，防止跨会话代答。
    """
    def confirm_callback(tool_name: str, args: dict) -> bool:
        confirm_id = str(uuid.uuid4())
        event = threading.Event()
        with _pending_confirms_lock:
            _pending_confirms[confirm_id] = {
                "event": event,
                "result": False,
                "session_id": session_id,
            }
        sse_write("confirm_request", {
            "id": confirm_id,
            "tool_name": tool_name,
            "args": args,
        })
        if event.wait(timeout=60):
            with _pending_confirms_lock:
                result = _pending_confirms.pop(confirm_id, {}).get("result", False)
            return result
        else:
            with _pending_confirms_lock:
                _pending_confirms.pop(confirm_id, None)
            return False

    return confirm_callback


# ── 读取前端 HTML ──

def _write_env(env_path: Path, content: str) -> None:
    """写 .env（临时文件 + 原子替换），带重试处理 Windows 瞬时文件锁。

    与 Recorder._write_atomic / agent.log 同源问题：杀软实时扫描会短暂锁定文件。
    5 次重试仍失败则显式抛出最后一个错误（不能在 except 块外裸 raise，
    否则触发 RuntimeError: No active exception to reraise），由调用方转为可读错误。
    """
    import time
    tmp = env_path.with_suffix(".env.tmp")
    last_error: OSError | None = None
    for attempt in range(5):
        try:
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, env_path)
            return
        except PermissionError as e:
            last_error = e
            if attempt < 4:
                time.sleep(0.2 * (attempt + 1))  # 0.2s → 0.4s → 0.6s → 0.8s
    # 5 次均失败：清理临时文件后抛出最后一个错误
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    raise last_error if last_error is not None else PermissionError("无法写入 .env")


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

    # ── CORS + 来源校验 ──

    def _get_allowed_origins(self) -> set[str]:
        """根据服务监听端口构造允许的本地源。"""
        port = self.server.server_address[1]
        return {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }

    def _cors(self):
        """CORS 头：仅回显本地源，拒绝跨域读取。"""
        origin = self.headers.get("Origin", "")
        if origin and origin in self._get_allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Credentials", "true")

    def _check_origin(self) -> bool:
        """校验请求来源是否为本地源。Origin 优先，退化到 Referer。"""
        allowed = self._get_allowed_origins()
        origin = self.headers.get("Origin", "")
        if origin:
            return origin in allowed
        referer = self.headers.get("Referer", "")
        if referer:
            return any(referer.startswith(a) for a in allowed)
        return False

    # ── Session 管理 ──

    def _read_session_cookie(self) -> str | None:
        """从 Cookie 头读取 session id。"""
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            morsel = cookie.get("session")
            return morsel.value if morsel else None
        except Exception:
            return None

    def _set_session_cookie(self, session_id: str):
        """在响应头设置 session cookie（HttpOnly + SameSite=Strict 防 CSRF）。"""
        self.send_header(
            "Set-Cookie",
            f"session={session_id}; Path=/; HttpOnly; SameSite=Strict",
        )

    # ── 公共响应头 ──

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
        # 预检请求：仅对本地源放行，挡住跨域预检
        if not self._check_origin():
            self.send_response(403)
            self.end_headers()
            return
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
        # 来源校验：仅允许本地浏览器请求
        if not self._check_origin():
            self._error(403, "禁止跨域请求")
            return
        # session 校验：POST 必须带有效 session cookie（防 curl/脚本盲发）
        session_id = self._read_session_cookie()
        if not session_id:
            self._error(403, "缺少 session，请通过浏览器访问")
            return
        self._session_id = session_id

        if self.path == "/setup":
            self._handle_setup()
        elif self.path == "/chat":
            if self._check_agent():
                self._handle_chat()
        elif self.path == "/task":
            if self._check_agent():
                self._handle_task()
        elif self.path == "/chain":
            if self._check_agent():
                self._handle_chain()
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

        try:
            # 写入 .env 文件（杀软瞬时锁用 _write_env 重试，异常则返回可读错误而非断连）
            env_path = ROOT / ".env"
            existing = {}
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, _, v = line.partition("=")
                        existing[k.strip()] = v.strip()

            existing["DEEPSEEK_API_KEY"] = api_key
            lines = [f"{k}={v}" for k, v in existing.items()]
            _write_env(env_path, "\n".join(lines) + "\n")

            # 重新加载配置（让新的 API Key 生效）
            os.environ["DEEPSEEK_API_KEY"] = api_key

            # 重置 Agent 状态
            reset_agent()

            # 尝试初始化
            agent = get_agent()
        except PermissionError as e:
            logger.error(f"/setup 写 .env 被拒绝（5 次重试均失败）: {e}")
            self._error(500,
                "无法写入 .env 文件（已被其他程序占用或安全软件拦截）。请排查："
                "①关闭打开 .env 的程序（记事本/VS Code/资源管理器选中预览）；"
                "②若仍失败，检查 Windows 安全中心的『受控文件夹访问』是否拦截了对 "
                "T:\\zhixuzhe\\.env 的写入。完成后请重试。")
            return
        except Exception as e:
            logger.error(f"/setup 处理失败（{type(e).__name__}）: {e}")
            self._error(500, f"设置过程中发生错误（{type(e).__name__}）: {e}")
            return

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
        """处理前端 HITL 确认响应（校验 session 一致，防跨会话代答）"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            confirm_id = body.get("id", "")
            approved = body.get("approved", False)
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        with _pending_confirms_lock:
            pending = _pending_confirms.get(confirm_id)
            if pending is None:
                self._error(404, "确认请求已过期或不存在")
                return
            # 关键校验：confirm_id 必须属于当前请求的 session
            if pending.get("session_id") != self._session_id:
                self._error(403, "session 不匹配，禁止代答")
                return
            pending["result"] = approved
            pending["event"].set()

        self._ok()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    # ── 页面 ──

    def _serve_page(self):
        # 首次访问下发 session cookie（HttpOnly + SameSite=Strict 防 CSRF）
        session_id = self._read_session_cookie()
        self.send_response(200)
        self._cors()
        if not session_id:
            self._set_session_cookie(secrets.token_urlsafe(32))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # 禁止缓存页面：旧版 JS/HTML 会绕过 session 校验流程，造成"网络错误"假象
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
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

        confirm_callback = _make_web_confirm_callback(sse_write, self._session_id)

        def tool_callback(event_type: str, data: dict) -> None:
            sse_write(event_type, data)

        try:
            response = agent.run(
                message,
                stream_callback=stream_callback,
                confirm_callback=confirm_callback,
                tool_callback=tool_callback,
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

            confirm_callback = _make_web_confirm_callback(sse_write, self._session_id)

            response = agent.task_runner.run(
                goal, verbose=True,
                verbose_callback=verbose_callback,
                confirm_callback=confirm_callback,
            )

            sse_write("task_done", {"content": response})
        except Exception as e:
            sse_write("error", {"content": str(e)})

    # ── 技能链模式 ──

    def _handle_chain(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            goal = body.get("goal", "").strip()
            skills = body.get("skills", [])
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        if not goal or not skills or not isinstance(skills, list):
            self._error(400, "goal 和 skills 不能为空")
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
            sse_write("chain_start", {"goal": goal, "skills": skills})

            def verbose_callback(msg: str) -> None:
                sse_write("chain_step", {"content": msg})

            confirm_callback = _make_web_confirm_callback(sse_write, self._session_id)

            from engine.core.orchestrator import SkillChain
            chain = SkillChain(
                agent.brain, agent.tools, agent.recorder,
                agent.skill_registry, agent.memory_manager,
            )
            response = chain.run(
                goal, skills,
                verbose=True,
                verbose_callback=verbose_callback,
                confirm_callback=confirm_callback,
            )

            sse_write("chain_done", {"content": response})
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
    # cmd（GBK 代码页）下 stdout 无法编码 emoji，统一降级为 replace，避免 UnicodeEncodeError 崩溃
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:
            pass

    print(f"\n  智序者 Web UI 启动中...")

    # 尝试预初始化
    agent = get_agent()
    if agent is not None:
        print(f"  Agent 就绪（{agent.tool_count} 个工具，{agent.skill_count} 个技能）")
    else:
        print(f"  [!] Agent 未就绪: {_agent_error}")
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
