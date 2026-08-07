"""search_file 工具 + code_search_explore 技能路由测试

纯本地运行，不依赖 DeepSeek API。
用法：python -m pytest engine/tests/test_search_file.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from engine.tools import search_file as sf
from engine.skills.registry import SkillRegistry
from engine.skills.web_research.skill import WebResearchSkill
from engine.skills.hardware_check.skill import HardwareCheckSkill
from engine.skills.code_explore.skill import CodeSearchSkill


@pytest.fixture
def fake_root(monkeypatch, tmp_path):
    """把 search_file 的项目根指向临时目录，并预置测试代码文件"""
    monkeypatch.setattr(sf, "_PROJECT_ROOT", tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def main():\n"
        "    print('hello world')\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "utils.py").write_text(
        "def helper():\n"
        "    # 关键逻辑: 缓存层\n"
        "    pass\n",
        encoding="utf-8",
    )
    # 二进制文件（应被跳过）
    (tmp_path / "src" / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    # 忽略目录内的文件（不应被搜索）
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.txt").write_text("def add(x): pass\n", encoding="utf-8")
    return tmp_path


def _build_registry() -> SkillRegistry:
    """按 factory 相同注册顺序构建技能注册表"""
    skills = SkillRegistry()
    skills.register(WebResearchSkill())
    skills.register(CodeSearchSkill())
    skills.register(HardwareCheckSkill())
    return skills


# ═══════════════════════════════════════════
# search_file 工具
# ═══════════════════════════════════════════

def test_search_file_hit(fake_root):
    """命中：返回 文件:行号: 内容 格式"""
    result = sf.search_file("def add", path="src")
    assert "app.py:1: def add(a, b)" in result
    assert "找到 1 条匹配" in result


def test_search_file_ignore_case(fake_root):
    """忽略大小写匹配"""
    result = sf.search_file("HELLO", path="src")
    assert "app.py:5: print('hello world')" in result


def test_search_file_no_hit(fake_root):
    """未命中返回提示"""
    result = sf.search_file("不存在的符号xyz", path="src")
    assert "未找到匹配" in result


def test_search_file_skips_binary(fake_root):
    """二进制文件被跳过"""
    result = sf.search_file("binary", path="src")
    assert "未找到匹配" in result


def test_search_file_skips_ignored_dirs(fake_root):
    """.git 等忽略目录不被搜索"""
    result = sf.search_file("def add", path=".")
    assert ".git" not in result
    assert "app.py:1" in result


def test_search_file_file_pattern(fake_root):
    """file_pattern 限定文件名"""
    result = sf.search_file("def ", path="src", file_pattern="*.py")
    assert "app.py" in result and "utils.py" in result


def test_search_file_out_of_root(fake_root):
    """搜索路径越界被拒绝"""
    outside = fake_root.parent  # 项目根之外
    result = sf.search_file("anything", path=str(outside))
    assert "不在项目目录内" in result


def test_search_file_invalid_regex(fake_root):
    """无效正则返回错误"""
    result = sf.search_file("[", path="src")
    assert "无效的正则表达式" in result


def test_search_file_max_results(fake_root):
    """结果条数上限生效"""
    (fake_root / "src" / "many.py").write_text(
        "\n".join(f"def func_{i}(): pass" for i in range(100)),
        encoding="utf-8",
    )
    result = sf.search_file("def func_", path="src", max_results=5)
    assert "找到 5 条匹配" in result
    assert "已达结果上限" in result


# ═══════════════════════════════════════════
# Router 匹配：code_search_explore
# ═══════════════════════════════════════════

def test_router_code_search_zh():
    """中文代码搜索意图命中 code_search_explore"""
    reg = _build_registry()
    for intent in ["搜索代码里的 add 函数", "代码里怎么调用 web_fetch", "看看代码结构"]:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == "code_search_explore", f"意图应命中 code: {intent}"


def test_router_code_search_en():
    """英文代码搜索意图命中 code_search_explore"""
    reg = _build_registry()
    for intent in ["search code for the cache layer", "explore the codebase", "find code that calls run_shell"]:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == "code_search_explore", f"意图应命中 code: {intent}"


def test_router_no_conflict_three_skills():
    """三类意图各命中各的技能，互不抢占"""
    reg = _build_registry()
    cases = [
        ("帮我搜索一下 Python 异步框架的资料", "web_research_summarize"),
        ("搜索代码里处理异常的部分", "code_search_explore"),
        ("检测硬件配置并判断 QLoRA 条件", "hardware_check"),
    ]
    for intent, expected in cases:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == expected, f"{intent} 应命中 {expected}，实际 {skill.name}"


def test_router_no_match():
    """无关意图不命中任何技能"""
    reg = _build_registry()
    for intent in ["今天晚饭吃什么", "讲个笑话", "你好"]:
        assert reg.match(intent) is None, f"不应命中技能: {intent}"
