"""对话历史持久化测试 —— 跨天自动归档（v1.5.1 修复）+ 轮次阈值断言

背景：恢复最近会话后新对话会覆盖写入旧日期文件，导致"今天的对话沉淀在
昨天文件里"（文件名永远旧日期，按天回溯误以为丢失）。ensure_today_session
在跨天时开今天的新文件并迁移历史。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from datetime import datetime

from engine.brain.base import Message
from engine.config import config
from engine.core.history import HistoryStore


def _write_session(store: HistoryStore, name: str, texts: list[str]) -> Path:
    """写入一个指定文件名的会话文件（绕过 new_session 的命名）"""
    path = store.dir / name
    with open(path, "w", encoding="utf-8") as f:
        for t in texts:
            f.write(json.dumps(Message(role="user", content=t).to_dict(), ensure_ascii=False) + "\n")
    return path


def test_same_day_session_not_archived(tmp_path: Path):
    """同日期会话文件直接复用，不归档"""
    store = HistoryStore(tmp_path)
    today = datetime.now().strftime("%Y%m%d")
    path = _write_session(store, f"{today}_120000_000000.jsonl", ["昨天的问题"])

    result = store.ensure_today_session(path)

    assert result == path
    assert store.current_session_name == path.name
    assert len(list(store.dir.glob("*.jsonl"))) == 1, "同日期不应新建文件"


def test_cross_day_session_archived_with_history(tmp_path: Path):
    """跨天归档：开今天的新文件并迁移全部历史，旧文件原样保留"""
    store = HistoryStore(tmp_path)
    old = _write_session(store, "20260801_120000_000000.jsonl", ["消息A", "消息B"])

    result = store.ensure_today_session(old)

    # 新文件属于今天，包含迁移的历史
    today = datetime.now().strftime("%Y%m%d")
    assert result.name.startswith(today)
    migrated = store.load(result)
    assert [m.content for m in migrated] == ["消息A", "消息B"]
    # 旧文件原样保留（未覆盖）
    assert old.exists()
    assert len(store.load(old)) == 2
    # 目录里现在有 2 个文件：旧归档 + 今天的新会话
    assert len(list(store.dir.glob("*.jsonl"))) == 2


def test_no_session_creates_new(tmp_path: Path):
    """无任何会话文件时开新会话"""
    store = HistoryStore(tmp_path)
    result = store.ensure_today_session()

    assert result.name.startswith(datetime.now().strftime("%Y%m%d"))


def test_agent_max_tool_rounds_doubled():
    """普通对话轮次阈值已提升两倍（15 → 30）"""
    assert config.agent.max_tool_rounds == 30, "max_tool_rounds 应为 30"
