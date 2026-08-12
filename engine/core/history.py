"""对话历史持久化 —— 重启后恢复上下文

将对话历史以 JSONL 格式存入 memory/conversations/，
每次启动自动恢复最近一次会话，reset 时开新会话。
"""

import json
from datetime import datetime
from pathlib import Path

from engine.brain.base import Message
from engine.log import get_logger

logger = get_logger(__name__)


def _deserialize(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=d.get("content", ""),
        tool_calls=d.get("tool_calls"),
        tool_call_id=d.get("tool_call_id"),
    )


class HistoryStore:
    """对话历史持久化存储。

    每次保存覆盖当前会话文件（完整写入），
    加载时读取全部行还原 Message 列表。
    """

    def __init__(self, root: Path):
        self.dir = root / "memory" / "conversations"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._current: Path | None = None

    @property
    def current_session_name(self) -> str | None:
        """当前会话文件名，未初始化时返回 None"""
        return self._current.name if self._current else None

    def set_current_session(self, path: Path) -> None:
        """设置当前会话文件路径"""
        self._current = path

    def new_session(self) -> Path:
        """开新会话文件，返回文件路径"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._current = self.dir / f"{ts}.jsonl"
        # 创建空文件以在磁盘上声明此会话
        self._current.touch()
        return self._current

    def latest_session(self) -> Path | None:
        """获取最近一次会话文件路径，没有则返回 None。

        过滤掉 0 字节空文件——reset 或异常退出可能残留空会话文件，
        时间戳最新会误导 latest_session 选中它，导致启动恢复到空历史。
        """
        files = sorted(
            f for f in self.dir.glob("*.jsonl") if f.stat().st_size > 0
        )
        return files[-1] if files else None

    @staticmethod
    def _session_date(path: Path) -> str:
        """从会话文件名提取日期（文件名前缀 YYYYMMDD）"""
        return Path(path).stem[:8]

    def ensure_today_session(self, path: Path | None = None) -> Path:
        """确保会话文件归属当天，返回实际使用的会话文件。

        跨天问题：恢复最近会话后，新对话会覆盖写入旧日期的文件，
        导致"今天的对话沉淀在昨天的文件里"（文件名永远是旧日期，
        按天回溯时误以为丢失）。修复：当最近会话文件日期不是今天时，
        开今天的新会话文件并把历史迁移过去（旧文件保持原样归档）。
        """
        target = path or self.latest_session()
        if target is None:
            return self.new_session()
        if self._session_date(target) == datetime.now().strftime("%Y%m%d"):
            self._current = target
            return target
        # 跨天归档：新文件先承载迁移的历史，旧文件原样保留
        new = self.new_session()
        messages = self.load(target)
        if messages:
            self.save(messages)
        logger.info(
            f"跨天归档会话: {Path(target).name} → {self._current.name}"
            f"（{len(messages)} 条历史迁移至今天）"
        )
        return self._current

    def save(self, messages: list[Message]) -> None:
        """保存当前完整历史到会话文件（原子写入，失败回退）。

        空消息列表时跳过写入，避免创建 0 字节空文件污染 latest_session。
        写入采用临时文件 + rename，防止进程崩溃在写一半损坏会话文件。
        Windows 上若 .tmp 文件被锁定（杀软扫描/残留），回退到直接覆盖写。
        """
        if self._current is None:
            self.new_session()
        # 空历史不写入，避免残留空文件
        if not messages:
            return

        tmp = self._current.with_suffix(self._current.suffix + ".tmp")
        # 清理可能残留的 tmp 文件（上一次崩溃/中断可能留下）
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

        try:
            with open(tmp, "w", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
            tmp.replace(self._current)  # 原子 rename（同卷）
        except PermissionError as e:
            # Windows 上 tmp 文件被锁定时（杀软/其他进程），回退到直接写
            logger.warning(f"原子写入失败（{e}），回退到直接写入")
            try:
                with open(self._current, "w", encoding="utf-8") as f:
                    for msg in messages:
                        f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
                # 清理 tmp 残留
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass
            except OSError as e2:
                logger.error(f"历史保存失败: {e2}")

    def load(self, filepath: Path) -> list[Message]:
        """从 JSONL 文件加载消息列表，跳过损坏行"""
        messages: list[Message] = []
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(_deserialize(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(
                        f"跳过损坏行 {filepath.name}:{i + 1} — {e}"
                    )
        return messages
