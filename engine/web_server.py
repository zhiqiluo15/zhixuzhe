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
import re
import secrets
import sys
import threading
import uuid
import datetime as _dt
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logger = logging.getLogger("zhixuzhe.web_server")

# 项目根
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"

# 确保项目根在 sys.path 中（脚本直接 python engine/web_server.py 运行时需要，
# 因为 Python 会把 engine/ 目录而非项目根加入 sys.path[0]）
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 版本唯一来源：engine/__init__.py（禁止在本模块硬编码版本字符串）
from engine import __version__ as ZX_VERSION

# 记忆条目解析（日记/经验可视化复用同一解析器）
from engine.core.memory_reader import parse_markdown_entries

# 页面版本占位符 → 注入统一版本号
_VERSION_TOKEN = "__ZX_VERSION__"


def _inject_version(html: str) -> str:
    """把页面中的 __ZX_VERSION__ 占位符替换为全局版本号"""
    return html.replace(_VERSION_TOKEN, ZX_VERSION)

# ── 全局状态 ──

_agent = None
_agent_error: str | None = None  # 初始化失败时的错误信息
_agent_lock = threading.Lock()

# ── 学习任务后台状态 ──
_learn_tasks: dict[str, dict] = {}  # learn_id → {"status", "node_id", "steps", "result", "error"}
_learn_lock = threading.Lock()

# ── HITL 确认状态 ──
_pending_confirms: dict[str, dict] = {}  # confirm_id → {"event", "result", "session_id"}
_pending_confirms_lock = threading.Lock()  # 保护 _pending_confirms 的并发访问

# ── 记忆/基因层可视化（只读）──

# 基因层文件白名单扩展名（可视化范围：engine/ + 根目录基因文件，不含灵魂层 memory/）
_GENOME_EXTS = {
    ".py", ".md", ".html", ".yaml", ".yml", ".txt", ".json", ".jsonl",
    ".bat", ".ps1", ".toml", ".ini", ".cfg", ".js", ".css",
}
_GENOME_ALLOW_NAMES = {".gitignore", ".env.example"}  # 无扩展名白名单文件
_GENOME_SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", "node_modules", "target", "venv", ".venv",
}
_GENOME_SKIP_FILES = {".env"}  # 密钥文件绝不展示
_GENOME_MAX_FILE = 1_000_000  # 单文件读取上限（1MB，防撑爆内存/上下文）

# 灵魂层/运行时目录——基因层文件查看 API 禁止访问
_GENOME_BLOCKED_SEGMENTS = {"memory", "logs", ".git"}

_MEMORY_KINDS = {
    "diary": ROOT / "memory" / "diary",
    "experience": ROOT / "memory" / "experience",
}


def _safe_resolve(base: Path, rel: str) -> Path | None:
    """把用户提供的相对路径解析到 base 内；穿越/绝对路径/不存在返回 None"""
    if not rel:
        return None
    p = Path(rel)
    if p.is_absolute():
        return None
    try:
        resolved = (base / p).resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(base.resolve()):
        return None
    if not resolved.exists():
        return None
    return resolved


def _list_genome_files() -> list[dict]:
    """扫描基因层文件（engine/ 递归 + 根目录基因文件），返回扁平清单（相对 ROOT 路径）"""
    out: list[dict] = []

    def scan(base: Path, prefix: str, recurse: bool) -> None:
        try:
            entries = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for entry in entries:
            name = entry.name
            rel = f"{prefix}/{name}" if prefix else name
            if entry.is_dir():
                if name in _GENOME_SKIP_DIRS or (not recurse):
                    continue
                scan(entry, rel, True)
            else:
                if name in _GENOME_SKIP_FILES:
                    continue
                ext = entry.suffix.lower()
                if ext not in _GENOME_EXTS and name not in _GENOME_ALLOW_NAMES:
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                out.append({
                    "path": rel,
                    "name": name,
                    "dir": prefix,
                    "size": size,
                    "ext": ext.lstrip(".") or name,
                })

    scan(ROOT / "engine", "engine", True)
    scan(ROOT, "", False)  # 根目录只取文件
    return out


def _build_genome_tree(files: list[dict]) -> list[dict]:
    """把扁平文件清单组装成嵌套树（供前端渲染目录树）"""
    root: list[dict] = []

    for f in files:
        parts = f["dir"].split("/") if f["dir"] else []
        cur = root
        cur_path = ""
        for part in parts:
            cur_path = f"{cur_path}/{part}" if cur_path else part
            node = next(
                (n for n in cur if n.get("name") == part and n["type"] == "dir"),
                None,
            )
            if node is None:
                node = {"path": cur_path, "name": part, "type": "dir", "children": []}
                cur.append(node)
            cur = node["children"]
        cur.append({
            "path": f["path"],
            "name": f["name"],
            "type": "file",
            "size": f["size"],
            "ext": f["ext"],
        })

    return root


def _load_genome_file(rel: str) -> dict | None:
    """读取基因层文件内容（仅 engine/ 与根目录基因文件，含穿越/密钥/二进制/大小防护）"""
    if not rel:
        return None
    path = _safe_resolve(ROOT, rel)
    if not path or not path.is_file():
        return None
    try:
        rel_str = path.relative_to(ROOT).as_posix()
    except ValueError:
        return None
    # 禁止访问灵魂层/运行时/密钥文件
    if any(seg in _GENOME_BLOCKED_SEGMENTS for seg in rel_str.split("/")):
        return None
    if path.name in _GENOME_SKIP_FILES:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > _GENOME_MAX_FILE:
        return None
    # 二进制检测：前 2KB 含 NUL 视为二进制（复用 file_io 的约定）
    try:
        with open(path, "rb") as fh:
            head = fh.read(2048)
        if b"\x00" in head:
            return {"path": rel_str, "name": path.name, "content": "", "size": size, "binary": True}
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return None
    return {"path": rel_str, "name": path.name, "content": content, "size": size, "binary": False}


def _load_session_list() -> list[dict]:
    """列出 memory/conversations/ 下所有非空会话，含消息数与首条用户消息预览"""
    conv_dir = ROOT / "memory" / "conversations"
    sessions: list[dict] = []
    if not conv_dir.exists():
        return sessions
    for f in sorted(conv_dir.glob("*.jsonl")):
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size == 0:
            continue
        name = f.name
        m = re.match(r"(\d{8})_(\d{6})_\d+\.jsonl", name)
        date_str = ""
        if m:
            date_str = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]} {m.group(2)[:2]}:{m.group(2)[2:4]}"
        count = 0
        preview = ""
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    count += 1
                    if not preview:
                        try:
                            d = json.loads(line)
                            if d.get("role") == "user" and d.get("content"):
                                preview = d["content"][:120]
                        except json.JSONDecodeError:
                            pass
        except OSError:
            continue
        sessions.append({
            "name": name, "date": date_str, "size": size,
            "messages": count, "preview": preview,
        })
    sessions.reverse()  # 最新在前
    return sessions


def _load_session_messages(name: str) -> dict | None:
    """读取单个会话的完整消息列表（文件名白名单正则 + 穿越防护）"""
    if not name or not re.fullmatch(r"\d{8}_\d{6}_\d+\.jsonl", name):
        return None
    path = _safe_resolve(ROOT / "memory" / "conversations", name)
    if not path or not path.is_file():
        return None
    messages: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                messages.append({
                    "role": d.get("role", ""),
                    "content": d.get("content", "") or "",
                    "tool_calls": d.get("tool_calls"),
                })
    except OSError:
        return None
    return {"name": name, "messages": messages}


def _load_memory_days(kind: str) -> list[dict]:
    """按天列出日记/经验文件及条目（只含预览，全文按需加载）"""
    base = _MEMORY_KINDS.get(kind)
    if base is None or not base.exists():
        return []
    days: list[dict] = []
    for f in sorted(base.glob("*.md"), reverse=True):  # 最新日期在前
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        entries: list[dict] = []
        for i, e in enumerate(parse_markdown_entries(content)):
            title = e["title"]
            entries.append({
                "index": i,
                "title": title,
                "is_task": title.startswith("[任务]"),
                "preview": e["body"][:200],
                "length": len(e["body"]),
            })
        if not entries:
            continue
        m = re.match(r"(\d{4})(\d{2})(\d{2})", f.name)
        date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
        days.append({
            "file": f.name, "date": date_str,
            "count": len(entries), "entries": entries,
        })
    return days


def _load_memory_entry(kind: str, file: str, index: int) -> dict | None:
    """读取单条日记/经验条目全文"""
    base = _MEMORY_KINDS.get(kind)
    if base is None or not file or not re.fullmatch(r"\d{8}\.md", file):
        return None
    path = _safe_resolve(base, file)
    if not path or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    entries = parse_markdown_entries(content)
    if index < 0 or index >= len(entries):
        return None
    e = entries[index]
    return {"file": file, "index": index, "title": e["title"], "body": e["body"]}


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
        _PAGE = _inject_version(html_path.read_text(encoding="utf-8"))
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
        elif self.path == "/profile":
            self._serve_profile_page()
        elif self.path == "/profile/data":
            self._serve_profile_data()
        elif self.path == "/knowledge":
            self._serve_knowledge_page()
        elif self.path == "/knowledge/list":
            self._serve_knowledge_list()
        elif self.path.startswith("/knowledge/view"):
            self._serve_knowledge_view()
        elif self.path == "/taxonomy":
            self._serve_taxonomy()
        elif self.path.startswith("/learn/status"):
            self._serve_learn_status()
        elif self.path == "/memory":
            self._serve_memory_page()
        elif self.path == "/memory/conversations":
            self._serve_memory_conversations()
        elif self.path.startswith("/memory/conversation?"):
            self._serve_memory_conversation()
        elif self.path.startswith("/memory/days?"):
            self._serve_memory_days()
        elif self.path.startswith("/memory/entry?"):
            self._serve_memory_entry()
        elif self.path == "/genome":
            self._serve_genome_page()
        elif self.path == "/genome/tree":
            self._serve_genome_tree()
        elif self.path.startswith("/genome/file?"):
            self._serve_genome_file()
        elif self.path == "/genome/changelog":
            self._serve_genome_changelog()
        elif self.path == "/genome/overview":
            self._serve_genome_overview()
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
        elif self.path == "/learn":
            if self._check_agent():
                self._handle_learn()
        elif self.path == "/knowledge/delete":
            if self._check_agent():
                self._handle_knowledge_delete()
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
            # 自动任务模式判断：普通对话入口先让 Brain 轻量判断
            if agent.should_auto_task(message):
                sse_write("task_start", {"goal": message, "auto": True})

                def auto_verbose_callback(msg: str) -> None:
                    sse_write("task_step", {"content": msg})

                response = agent.task_runner.run(
                    message, verbose=True,
                    verbose_callback=auto_verbose_callback,
                    confirm_callback=confirm_callback,
                )
                sse_write("task_done", {"content": response})
                return

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

    # ── 知识面板页面 ──

    def _serve_profile_page(self):
        """提供能力面板页面"""
        session_id = self._read_session_cookie()
        self.send_response(200)
        self._cors()
        if not session_id:
            self._set_session_cookie(secrets.token_urlsafe(32))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        profile_path = WEB_DIR / "profile.html"
        if profile_path.exists():
            self.wfile.write(_inject_version(profile_path.read_text(encoding="utf-8")).encode())
        else:
            self.wfile.write("<h1>profile.html 未找到</h1>".encode())

    def _serve_profile_data(self):
        """返回能力档案 JSON"""
        agent = get_agent()
        self._ok()
        profile_data = {"languages": {}, "history": [], "skills": []}
        if agent.profile_manager:
            profile_data = agent.profile_manager.load()
        if agent.skill_registry:
            profile_data["skills"] = [
                {"name": s.name, "description": s.description}
                for s in agent.skill_registry.list_all()
            ]
        self.wfile.write(json.dumps(profile_data, ensure_ascii=False).encode())

    def _serve_taxonomy(self):
        """返回知识分类树 JSON（含已学状态）"""
        agent = get_agent()
        if not agent.taxonomy:
            self._error(500, "知识分类系统未初始化")
            return

        self._ok()
        categories = agent.taxonomy.to_dict()

        # 注入每个节点的已学状态（按具体主题名判断，而非按领域count）
        if agent.profile_manager:
            for cat in categories:
                for node in cat.get("children", []):
                    parent = node.get("parent", "")
                    topic_name = node.get("name", "")
                    node["learned"] = agent.profile_manager.has_topic(parent, topic_name)

        self.wfile.write(json.dumps({"categories": categories}, ensure_ascii=False).encode())

    # ── 知识管理 ──

    def _serve_knowledge_page(self):
        """提供知识管理页面"""
        session_id = self._read_session_cookie()
        self.send_response(200)
        self._cors()
        if not session_id:
            self._set_session_cookie(secrets.token_urlsafe(32))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        knowledge_path = WEB_DIR / "knowledge.html"
        if knowledge_path.exists():
            self.wfile.write(_inject_version(knowledge_path.read_text(encoding="utf-8")).encode())
        else:
            self.wfile.write("<h1>knowledge.html 未找到</h1>".encode())

    def _serve_knowledge_list(self):
        """返回知识列表 JSON：按领域分组，含每个知识的元数据"""
        self._ok()
        knowledge_dir = ROOT / "memory" / "knowledge" / "languages"
        domains = []
        total = 0

        if knowledge_dir.exists():
            for parent_dir in sorted(knowledge_dir.iterdir()):
                if not parent_dir.is_dir():
                    continue
                items = []
                for kf in sorted(parent_dir.glob("*.md")):
                    try:
                        content = kf.read_text(encoding="utf-8")
                        # 解析元数据
                        title = kf.stem
                        date = ""
                        mtime = kf.stat().st_mtime
                        date = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

                        # 从 header 中提取学习时间
                        for line in content.split("\n")[:10]:
                            if line.startswith("> 学习时间："):
                                date = line.split("：", 1)[1].strip().rstrip("  ")
                                break

                        # 计算字数（粗略）
                        word_count = len(content)

                        # 提取摘要（第一个 ## 之后的前150字）
                        summary = ""
                        body_start = content.find("\n---\n")
                        if body_start != -1:
                            body = content[body_start + 5:].strip()
                            # 去掉第一个 ## 标题行
                            lines = body.split("\n")
                            for line in lines:
                                if line.startswith("## ") or line.startswith("### "):
                                    continue
                                if line.strip():
                                    summary = line.strip()[:150]
                                    break
                            if not summary:
                                summary = body[:150].replace("\n", " ").strip()
                        else:
                            summary = content[:150].replace("\n", " ").strip()

                        items.append({
                            "topic": kf.stem,
                            "parent": parent_dir.name,
                            "title": title,
                            "date": date,
                            "word_count": word_count,
                            "summary": summary,
                        })
                        total += 1
                    except Exception:
                        continue
                if items:
                    domains.append({
                        "name": parent_dir.name,
                        "count": len(items),
                        "items": items,
                    })

        self.wfile.write(json.dumps({
            "domains": domains,
            "total": total,
        }, ensure_ascii=False).encode())

    def _serve_knowledge_view(self):
        """返回单个知识文件的完整内容"""
        import urllib.parse
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        parent = params.get("parent", [""])[0]
        topic = params.get("topic", [""])[0]

        if not parent or not topic:
            self._error(400, "parent 和 topic 参数不能为空")
            return

        # 路径安全校验：禁止 ../ 穿越
        if ".." in parent or ".." in topic or "/" in topic or "\\" in topic:
            self._error(400, "无效的路径参数")
            return

        knowledge_path = ROOT / "memory" / "knowledge" / "languages" / parent / f"{topic}.md"
        if not knowledge_path.exists() or not knowledge_path.is_file():
            self._error(404, "知识文件不存在")
            return

        try:
            content = knowledge_path.read_text(encoding="utf-8")
        except Exception as e:
            self._error(500, f"读取失败: {e}")
            return

        self._ok()
        self.wfile.write(json.dumps({
            "parent": parent,
            "topic": topic,
            "content": content,
        }, ensure_ascii=False).encode())

    def _handle_knowledge_delete(self):
        """删除知识文件"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            parent = body.get("parent", "").strip()
            topic = body.get("topic", "").strip()
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        if not parent or not topic:
            self._error(400, "parent 和 topic 不能为空")
            return

        if ".." in parent or ".." in topic or "/" in topic or "\\" in topic:
            self._error(400, "无效的路径参数")
            return

        knowledge_path = ROOT / "memory" / "knowledge" / "languages" / parent / f"{topic}.md"
        if not knowledge_path.exists():
            self._error(404, "知识文件不存在")
            return

        try:
            knowledge_path.unlink()
        except Exception as e:
            self._error(500, f"删除失败: {e}")
            return

        self._ok()
        self.wfile.write(json.dumps({"status": "ok", "deleted": f"{parent}/{topic}"}, ensure_ascii=False).encode())

    # ── 学习任务状态查询 ──

    def _serve_learn_status(self):
        """GET /learn/status?learn_id=X 查询学习任务进度"""
        import urllib.parse
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        learn_id = params.get("learn_id", [""])[0]

        self._ok()
        with _learn_lock:
            task = _learn_tasks.get(learn_id, {"status": "not_found"})
        self.wfile.write(json.dumps(task, ensure_ascii=False).encode())

    # ── 记忆回顾页 ──

    def _serve_memory_page(self):
        """GET /memory → 记忆回顾页（对话历史 + 日记 + 经验）"""
        session_id = self._read_session_cookie()
        self.send_response(200)
        self._cors()
        if not session_id:
            self._set_session_cookie(secrets.token_urlsafe(32))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        path = WEB_DIR / "memory.html"
        if path.exists():
            self.wfile.write(_inject_version(path.read_text(encoding="utf-8")).encode())
        else:
            self.wfile.write("<h1>memory.html 缺失</h1>".encode("utf-8"))

    def _serve_memory_conversations(self):
        """GET /memory/conversations → 会话列表"""
        self._ok()
        sessions = _load_session_list()
        self.wfile.write(json.dumps({"sessions": sessions, "total": len(sessions)}, ensure_ascii=False).encode())

    def _serve_memory_conversation(self):
        """GET /memory/conversation?file=X → 单个会话完整消息"""
        import urllib.parse
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        data = _load_session_messages(params.get("file", [""])[0])
        if data is None:
            self._error(404, "会话不存在")
            return
        self._ok()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _serve_memory_days(self):
        """GET /memory/days?kind=diary|experience → 按天分组的条目列表（含预览）"""
        import urllib.parse
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        kind = params.get("kind", ["diary"])[0]
        if kind not in _MEMORY_KINDS:
            self._error(400, "kind 必须是 diary 或 experience")
            return
        self._ok()
        days = _load_memory_days(kind)
        self.wfile.write(json.dumps({"kind": kind, "days": days}, ensure_ascii=False).encode())

    def _serve_memory_entry(self):
        """GET /memory/entry?kind=diary&file=20260808.md&index=3 → 单条条目全文"""
        import urllib.parse
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        kind = params.get("kind", [""])[0]
        file = params.get("file", [""])[0]
        try:
            index = int(params.get("index", ["-1"])[0])
        except ValueError:
            index = -1
        data = _load_memory_entry(kind, file, index)
        if data is None:
            self._error(404, "条目不存在")
            return
        self._ok()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    # ── 基因层可视化页 ──

    def _serve_genome_page(self):
        """GET /genome → 基因层可视化页（目录树 + 文件查看 + 进化史）"""
        session_id = self._read_session_cookie()
        self.send_response(200)
        self._cors()
        if not session_id:
            self._set_session_cookie(secrets.token_urlsafe(32))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        path = WEB_DIR / "genome.html"
        if path.exists():
            self.wfile.write(_inject_version(path.read_text(encoding="utf-8")).encode())
        else:
            self.wfile.write("<h1>genome.html 缺失</h1>".encode("utf-8"))

    def _serve_genome_tree(self):
        """GET /genome/tree → 基因层文件树"""
        self._ok()
        files = _list_genome_files()
        tree = _build_genome_tree(files)
        self.wfile.write(json.dumps({"files": len(files), "tree": tree}, ensure_ascii=False).encode())

    def _serve_genome_file(self):
        """GET /genome/file?path=engine/core/loop.py → 文件内容（只读 + 安全校验）"""
        import urllib.parse
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        data = _load_genome_file(params.get("path", [""])[0])
        if data is None:
            self._error(404, "文件不存在或不可访问")
            return
        self._ok()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _serve_genome_changelog(self):
        """GET /genome/changelog → CHANGELOG.md 原始内容（进化史渲染用）"""
        path = ROOT / "CHANGELOG.md"
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        self._ok()
        self.wfile.write(json.dumps({"content": content}, ensure_ascii=False).encode())

    def _serve_genome_overview(self):
        """GET /genome/overview → 版本/工具数/技能数概览"""
        status = get_agent_status()
        tools = skills = 0
        if status["ready"]:
            try:
                agent = get_agent()
                tools = agent.tool_count
                skills = agent.skill_count
            except Exception:
                pass
        self._ok()
        self.wfile.write(json.dumps({
            "version": ZX_VERSION,
            "tools": tools,
            "skills": skills,
            "ready": status["ready"],
        }, ensure_ascii=False).encode())

    # ── 学习任务 ──

    def _handle_learn(self):
        """启动知识学习任务（后台线程，SSE 返回 learn_id 供轮询）"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            node_id = body.get("node_id", "").strip()
        except (ValueError, json.JSONDecodeError):
            self._error(400, "无效请求体")
            return

        if not node_id:
            self._error(400, "node_id 不能为空")
            return

        agent = get_agent()
        if not agent.taxonomy:
            self._error(500, "知识分类系统未初始化")
            return

        node = agent.taxonomy.get_node(node_id)
        if not node:
            self._error(400, f"未知主题: {node_id}")
            return

        learn_id = str(uuid.uuid4())

        with _learn_lock:
            _learn_tasks[learn_id] = {
                "status": "running",
                "node_id": node_id,
                "name": node.name,
                "parent": node.parent,
                "step": 0,
                "step_text": "启动中...",
                "total_steps": 0,
                "result": "",
                "error": "",
            }

        # 后台执行
        t = threading.Thread(
            target=_run_learn_in_background,
            args=(learn_id, agent, node),
            daemon=True,
        )
        t.start()

        self._ok()
        self.wfile.write(json.dumps({
            "status": "started",
            "learn_id": learn_id,
            "node_id": node_id,
        }, ensure_ascii=False).encode())

    # ── 重置 ──

    def _handle_reset(self):
        agent = get_agent()
        agent.history.clear()
        if agent.history_store:
            agent.history_store.new_session()
        self._ok()
        self.wfile.write(json.dumps({"status": "ok"}).encode())


def _run_learn_in_background(learn_id: str, agent, node) -> None:
    """后台执行学习任务，更新 _learn_tasks 状态。

    使用 KnowledgeLearningSkill 罐装计划（5步，含重试），而非 LLM 即兴规划。
    关键流程：
    1. 使用罐装 Skill 计划（搜索→clone→探索→读源码→报告），单步失败重试1次
    2. clone 失败降级为 web_fetch README
    3. 成功判定（方案B）：材料步骤（搜索/克隆）至少一个成功，且失败步骤不超过半数
    4. 成功则：写知识文件（幂等覆盖）+ 更新能力档案（幂等，复习不重复计数）+ 反思经验
    5. 异常兜底：任何异常都不击穿线程，记入 error
    """
    try:
        from engine.skills.knowledge_learning.skill import (
            KnowledgeLearningSkill,
            is_learning_failed,
        )

        learn_skill = KnowledgeLearningSkill(
            topic_name=node.name,
            search_query=agent.taxonomy.generate_search_query(node.id),
            repo_hint=node.repo_hint or "",
        )
        plan = learn_skill.plan(node.name)
        goal = f"学习计算机知识主题：{node.name}（属于{node.parent}领域）"

        with _learn_lock:
            task = _learn_tasks.get(learn_id, {})
            task["total_steps"] = len(plan)
            task["step"] = 0
            task["step_text"] = "准备中..."

        def progress_callback(msg: str) -> None:
            with _learn_lock:
                t = _learn_tasks.get(learn_id, {})
                t["step_text"] = msg[:120]
                step_match = re.search(r"\[(\d+)/(\d+)\]", msg)
                if step_match:
                    t["step"] = int(step_match.group(1))
                    t["total_steps"] = int(step_match.group(2))

        # 注入记忆上下文
        memory_context = ""
        if agent.memory_manager:
            memory_context = agent.memory_manager.build_context(goal)

        # 执行计划（单步重试1次）
        step_results = []
        for i, step in enumerate(plan):
            step_ok = False
            for attempt in range(2):
                try:
                    progress_callback(f"⏳ [{i + 1}/{len(plan)}] {step[:50]}...")
                    result = agent.task_runner._execute_step(
                        goal, step, i, plan, step_results[:i],
                        None,  # Web 端学习暂不经过 HITL 确认（clone/read 不需要审批）
                        memory_context if i == 0 else "",
                    )
                    step_results.append(result)
                    progress_callback(f"✅ [{i + 1}/{len(plan)}] 步骤完成")
                    step_ok = True
                    break
                except Exception as e:
                    logger.warning(f"学习步骤 {i+1} 第{attempt+1}次尝试失败: {e}")
                    if attempt == 0:
                        progress_callback(f"⚠️ 步骤 {i+1} 失败，重试...")
                    else:
                        step_results.append(f"执行失败（重试后仍失败）: {e}")
                        progress_callback(f"❌ 步骤 {i+1} 失败，跳过")

        # 综合结论
        try:
            response = agent.task_runner._synthesize(goal, plan, step_results)
        except Exception as e:
            response = "学习过程部分失败，但已获取以下信息：\n\n" + "\n\n".join(
                sr for sr in step_results if sr and not sr.startswith("执行失败")
            )

        # 判断学习是否成功（方案B：材料步骤至少成功一个，失败步骤不过半）
        if is_learning_failed(step_results):
            with _learn_lock:
                _learn_tasks[learn_id]["status"] = "failed"
                _learn_tasks[learn_id]["error"] = "学习失败：未获取到可学习的材料或失败步骤过多，知识库和档案均未更新。"
            return

        # 写知识文件（幂等覆盖）
        try:
            agent.recorder.record_knowledge(
                parent=node.parent,
                topic=node.name,
                report=response,
            )
        except Exception as e:
            logger.warning(f"知识写入失败（不阻断流程）: {e}")

        # 更新能力档案（幂等：新学+1，复习不计数）
        try:
            if agent.profile_manager:
                agent.profile_manager.record_learning(
                    parent=node.parent,
                    topic=node.name,
                    summary=response[:200],
                )
        except Exception as e:
            logger.warning(f"档案更新失败（不阻断流程）: {e}")

        # 反思经验
        try:
            agent.task_runner.reflect_experience(goal, response)
        except Exception:
            pass

        with _learn_lock:
            _learn_tasks[learn_id]["status"] = "done"
            _learn_tasks[learn_id]["result"] = response[:500]

    except Exception as e:
        logger.error(f"学习任务异常: {e}", exc_info=True)
        with _learn_lock:
            _learn_tasks[learn_id]["status"] = "failed"
            _learn_tasks[learn_id]["error"] = str(e)


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
