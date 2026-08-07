"""list_files / batch_files 工具 + file_manage_batch 技能路由测试

纯本地运行，不依赖 DeepSeek API。
用法：python -m pytest engine/tests/test_file_manage.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from engine.tools import file_manage as fm
from engine.skills.registry import SkillRegistry
from engine.skills.web_research.skill import WebResearchSkill
from engine.skills.hardware_check.skill import HardwareCheckSkill
from engine.skills.code_explore.skill import CodeSearchSkill
from engine.skills.data_analysis.skill import DataAnalysisSkill
from engine.skills.file_manage.skill import FileManageSkill


@pytest.fixture
def fake_root(monkeypatch, tmp_path):
    """把 file_manage 的项目根指向临时目录，并预置测试文件"""
    monkeypatch.setattr(fm, "_PROJECT_ROOT", tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# 旧标题\n正文\n", encoding="utf-8")
    (tmp_path / "logs" / "a.log").write_text("info\n", encoding="utf-8")
    (tmp_path / "logs" / "b.log").write_text("error\n", encoding="utf-8")
    (tmp_path / "root.log").write_text("root-level\n", encoding="utf-8")
    (tmp_path / "tmp" / "old_tmp.txt").parent.mkdir(exist_ok=True)
    (tmp_path / "tmp" / "old_tmp.txt").write_text("trash\n", encoding="utf-8")
    # 二进制文件
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    return tmp_path


def _build_registry() -> SkillRegistry:
    """按 factory 相同注册顺序构建技能注册表"""
    skills = SkillRegistry()
    skills.register(WebResearchSkill())
    skills.register(CodeSearchSkill())
    skills.register(DataAnalysisSkill())
    skills.register(FileManageSkill())
    skills.register(HardwareCheckSkill())
    return skills


# ═══════════════════════════════════════════
# list_files
# ═══════════════════════════════════════════

def test_list_files(fake_root):
    """列出根目录文件"""
    result = fm.list_files(".")
    assert "app.py" in result
    assert "README.md" in result
    assert "logs" not in result  # 非递归不含子目录文件
    assert "共 " in result


def test_list_files_glob(fake_root):
    """glob 过滤"""
    result = fm.list_files(".", pattern="*.py")
    assert "app.py" in result
    assert "README.md" not in result


def test_list_files_recursive(fake_root):
    """递归列出包含子目录"""
    result = fm.list_files(".", pattern="*.log", recursive=True)
    assert "logs" in result and "a.log" in result


def test_list_files_out_of_root(fake_root):
    """越界路径被拒绝"""
    result = fm.list_files(str(fake_root.parent))
    assert "不在项目目录内" in result


def test_list_files_not_found(fake_root):
    """目录不存在"""
    result = fm.list_files("nope_dir")
    assert "路径不存在" in result


# ═══════════════════════════════════════════
# batch_files
# ═══════════════════════════════════════════

def test_batch_rename_dry_run(fake_root):
    """rename dry_run 只预览不执行"""
    result = fm.batch_files("rename", "*.md", replace_from="README", replace_to="GUIDE")
    assert "README.md → GUIDE.md" in result
    assert "dry_run 预览" in result
    # 文件未被修改
    assert (fake_root / "README.md").exists()


def test_batch_rename_execute(fake_root):
    """rename 实际执行"""
    result = fm.batch_files(
        "rename", "*.md", replace_from="README", replace_to="GUIDE", dry_run=False,
    )
    assert "✅ README.md → GUIDE.md" in result
    assert not (fake_root / "README.md").exists()
    assert (fake_root / "GUIDE.md").exists()


def test_batch_rename_no_change_skipped(fake_root):
    """rename 无变化的文件被跳过"""
    result = fm.batch_files("rename", "*.py", replace_from="xxx", replace_to="yyy")
    assert "跳过（名称无变化）" in result


def test_batch_move(fake_root):
    """move 根目录日志到目标目录"""
    result = fm.batch_files(
        "move", "*.log", target="archive", dry_run=False,
    )
    assert "✅ root.log → archive/root.log" in result
    assert (fake_root / "archive" / "root.log").exists()
    assert not (fake_root / "root.log").exists()


def test_batch_move_subdir(fake_root):
    """move 子目录文件"""
    result = fm.batch_files(
        "move", "tmp/*.txt", target="archive", dry_run=False,
    )
    assert "✅ tmp/old_tmp.txt → archive/old_tmp.txt" in result
    assert (fake_root / "archive" / "old_tmp.txt").exists()


def test_batch_copy(fake_root):
    """copy 保留源文件"""
    result = fm.batch_files(
        "copy", "*.py", target="backup", dry_run=False,
    )
    assert (fake_root / "app.py").exists()  # 源保留
    assert (fake_root / "backup" / "app.py").exists()


def test_batch_delete_dry_run(fake_root):
    """delete dry_run 不删除"""
    result = fm.batch_files("delete", "tmp/*.txt")
    assert "删除: tmp/old_tmp.txt" in result
    assert (fake_root / "tmp" / "old_tmp.txt").exists()


def test_batch_delete_execute(fake_root):
    """delete 实际执行"""
    result = fm.batch_files("delete", "tmp/*.txt", dry_run=False)
    assert "✅ 已删除: tmp/old_tmp.txt" in result
    assert not (fake_root / "tmp" / "old_tmp.txt").exists()


def test_batch_replace(fake_root):
    """replace 内容替换"""
    result = fm.batch_files(
        "replace", "README.md", replace_from="旧标题", replace_to="新标题", dry_run=False,
    )
    assert "替换 1 处" in result
    assert "新标题" in (fake_root / "README.md").read_text(encoding="utf-8")


def test_batch_replace_no_match_skipped(fake_root):
    """replace 无匹配内容跳过"""
    result = fm.batch_files("replace", "README.md", replace_from="不存在的内容", replace_to="x")
    assert "跳过（无匹配内容）" in result
    assert "旧标题" in (fake_root / "README.md").read_text(encoding="utf-8")


def test_batch_replace_skips_binary(fake_root):
    """replace 跳过二进制文件"""
    result = fm.batch_files("replace", "blob.bin", replace_from="a", replace_to="b")
    assert "跳过（二进制）" in result


def test_batch_invalid_action(fake_root):
    """无效操作类型"""
    result = fm.batch_files("explode", "*")
    assert "不支持的操作" in result


def test_batch_rename_requires_from(fake_root):
    """rename 缺 replace_from"""
    result = fm.batch_files("rename", "*.md")
    assert "需要 replace_from" in result


def test_batch_move_requires_target(fake_root):
    """move 缺 target"""
    result = fm.batch_files("move", "*.py")
    assert "需要 target" in result


def test_batch_target_out_of_root(fake_root):
    """目标目录越界被拒绝"""
    result = fm.batch_files("move", "*.py", target=str(fake_root.parent / "out"))
    assert "目标目录不在项目目录内" in result


def test_batch_no_match(fake_root):
    """无匹配文件"""
    result = fm.batch_files("delete", "*.xyz")
    assert "未找到匹配" in result


# ═══════════════════════════════════════════
# Router 匹配：file_manage_batch
# ═══════════════════════════════════════════

def test_router_file_manage_zh():
    """中文文件管理意图命中 file_manage_batch"""
    reg = _build_registry()
    for intent in ["批量重命名这些临时文件", "帮我整理一下文件", "清理日志目录", "批量删除 tmp 文件"]:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == "file_manage_batch", f"意图应命中 file_manage: {intent}"


def test_router_file_manage_en():
    """英文文件管理意图命中 file_manage_batch"""
    reg = _build_registry()
    # 注：带冠词的说法（如 "organize the project files"）不含触发词子串，由 LLM 即兴规划兜底
    for intent in ["batch rename files in logs", "clean up temp files", "organize project files"]:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == "file_manage_batch", f"意图应命中 file_manage: {intent}"


def test_router_no_conflict_five_skills():
    """五类意图各命中各的技能，互不抢占"""
    reg = _build_registry()
    cases = [
        ("帮我搜索一下 Python 异步框架的资料", "web_research_summarize"),
        ("搜索代码里处理异常的部分", "code_search_explore"),
        ("分析一下数据文件里的销售趋势", "data_analysis_visual"),
        ("批量重命名这些临时文件", "file_manage_batch"),
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
