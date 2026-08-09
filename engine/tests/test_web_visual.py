"""记忆/基因层 Web 可视化 API 测试 —— 路径安全 + 解析正确性"""

from pathlib import Path

import pytest

import engine.web_server as ws


# ── _safe_resolve 路径安全 ──

def test_safe_resolve_normal(tmp_path):
    target = tmp_path / "a" / "b.txt"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    assert ws._safe_resolve(tmp_path, "a/b.txt") == target


def test_safe_resolve_rejects_traversal(tmp_path):
    assert ws._safe_resolve(tmp_path, "../outside.txt") is None
    assert ws._safe_resolve(tmp_path, "a/../../outside.txt") is None


def test_safe_resolve_rejects_absolute(tmp_path):
    assert ws._safe_resolve(tmp_path, str(tmp_path / "a.txt")) is None


def test_safe_resolve_rejects_nonexistent(tmp_path):
    assert ws._safe_resolve(tmp_path, "nope.txt") is None


def test_safe_resolve_rejects_empty(tmp_path):
    assert ws._safe_resolve(tmp_path, "") is None


# ── _list_genome_files / _build_genome_tree ──

def test_list_genome_files_covers_engine():
    files = ws._list_genome_files()
    paths = [f["path"] for f in files]
    # 核心引擎文件必须在列（存在性稳定）
    assert "engine/core/loop.py" in paths
    assert "engine/core/memory_reader.py" in paths
    # 根目录基因文件在列
    assert "CHANGELOG.md" in paths
    # 密钥/运行时目录绝不在列（.gitignore 是基因文件，需按目录段而非子串判断）
    assert not any(f["name"] == ".env" for f in files)
    assert not any(seg == ".git" for f in files for seg in f["path"].split("/"))
    assert not any("__pycache__" in f["path"] for f in files)


def test_build_genome_tree_structure():
    files = [
        {"path": "engine/core/loop.py", "dir": "engine/core", "name": "loop.py", "size": 1, "ext": "py"},
        {"path": "engine/core/task.py", "dir": "engine/core", "name": "task.py", "size": 1, "ext": "py"},
        {"path": "engine/__init__.py", "dir": "engine", "name": "__init__.py", "size": 1, "ext": "py"},
        {"path": "CHANGELOG.md", "dir": "", "name": "CHANGELOG.md", "size": 1, "ext": "md"},
    ]
    tree = ws._build_genome_tree(files)
    engine_node = next(n for n in tree if n["name"] == "engine" and n["type"] == "dir")
    core_node = next(n for n in engine_node["children"] if n["name"] == "core")
    assert len(core_node["children"]) == 2  # loop.py + task.py
    assert any(n["name"] == "__init__.py" for n in engine_node["children"])
    assert any(n["name"] == "CHANGELOG.md" and n["type"] == "file" for n in tree)


# ── _load_genome_file ──

def test_load_genome_file_reads_python():
    data = ws._load_genome_file("engine/__init__.py")
    assert data is not None and data["binary"] is False
    assert "__version__" in data["content"]
    assert data["path"] == "engine/__init__.py"


def test_load_genome_file_blocks_soul_layer():
    # 灵魂层 memory/ 与运行时 logs/ 禁止通过基因层接口读取
    assert ws._load_genome_file("memory/diary/20260808.md") is None
    assert ws._load_genome_file("logs/agent.log") is None


def test_load_genome_file_blocks_traversal():
    assert ws._load_genome_file("../CHANGELOG.md") is None
    assert ws._load_genome_file("engine/../../.env") is None


def test_load_genome_file_nonexistent():
    assert ws._load_genome_file("engine/nope.py") is None
    assert ws._load_genome_file("") is None


# ── _load_session_messages 文件名白名单 ──

def test_session_messages_rejects_bad_names():
    assert ws._load_session_messages("../../etc/passwd") is None
    assert ws._load_session_messages("C:/x.jsonl") is None
    assert ws._load_session_messages("notes.jsonl") is None  # 不匹配时间戳格式
    assert ws._load_session_messages("") is None


# ── _load_memory_days / _load_memory_entry（tmp 目录注入） ──

@pytest.fixture
def fake_memory(tmp_path, monkeypatch):
    diary = tmp_path / "diary"
    exp = tmp_path / "experience"
    diary.mkdir()
    exp.mkdir()
    (diary / "20260101.md").write_text(
        "# 2026-01-01 文件头\n\n"
        "## 10:00:00\n第一条正文内容。\n\n"
        "## [任务] 11:00:00\n任务正文。\n",
        encoding="utf-8",
    )
    (exp / "20260102.md").write_text(
        "# 经验\n\n## 09:00:00\n经验一。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ws, "_MEMORY_KINDS", {"diary": diary, "experience": exp})
    return diary, exp


def test_load_memory_days(fake_memory):
    days = ws._load_memory_days("diary")
    assert len(days) == 1
    assert days[0]["date"] == "2026-01-01"
    assert days[0]["count"] == 2
    assert days[0]["entries"][0]["is_task"] is False
    assert days[0]["entries"][1]["is_task"] is True
    assert days[0]["entries"][0]["preview"]  # 预览非空


def test_load_memory_days_invalid_kind(fake_memory):
    assert ws._load_memory_days("unknown") == []


def test_load_memory_entry(fake_memory):
    data = ws._load_memory_entry("diary", "20260101.md", 1)
    assert data is not None
    assert data["title"].startswith("[任务]")
    assert "任务正文" in data["body"]
    # 越界/非法参数
    assert ws._load_memory_entry("diary", "20260101.md", 99) is None
    assert ws._load_memory_entry("diary", "../evil.md", 0) is None
    assert ws._load_memory_entry("diary", "20260101.txt", 0) is None  # 扩展名不匹配
    assert ws._load_memory_entry("diary", "", 0) is None
