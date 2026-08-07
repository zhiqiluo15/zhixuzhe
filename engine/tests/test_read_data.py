"""read_data 工具 + data_analysis_visual 技能路由测试

纯本地运行，不依赖 DeepSeek API。
用法：python -m pytest engine/tests/test_read_data.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from engine.tools import read_data as rd
from engine.skills.registry import SkillRegistry
from engine.skills.web_research.skill import WebResearchSkill
from engine.skills.hardware_check.skill import HardwareCheckSkill
from engine.skills.code_explore.skill import CodeSearchSkill
from engine.skills.data_analysis.skill import DataAnalysisSkill


@pytest.fixture
def fake_root(monkeypatch, tmp_path):
    """把 read_data 的项目根指向临时目录，并预置测试数据文件"""
    monkeypatch.setattr(rd, "_PROJECT_ROOT", tmp_path)

    # CSV：数值列 + 类别列混合
    (tmp_path / "sales.csv").write_text(
        "product,category,price,quantity\n"
        "apple,fruit,3.5,100\n"
        "banana,fruit,2.0,150\n"
        "carrot,vegetable,1.5,80\n"
        "milk,dairy,5.0,60\n",
        encoding="utf-8",
    )
    # JSON 数组
    (tmp_path / "users.json").write_text(
        '[{"name": "a", "age": 20}, {"name": "b", "age": 30}, {"name": "c", "age": 40}]',
        encoding="utf-8",
    )
    # JSONL
    (tmp_path / "log.jsonl").write_text(
        '{"level": "info", "ms": 12}\n'
        '{"level": "error", "ms": 45}\n'
        '{"level": "info", "ms": 8}\n',
        encoding="utf-8",
    )
    # JSON 对象
    (tmp_path / "meta.json").write_text(
        '{"version": "1.2", "features": ["a", "b"], "count": 42}',
        encoding="utf-8",
    )
    # 二进制
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02data")
    return tmp_path


def _build_registry() -> SkillRegistry:
    """按 factory 相同注册顺序构建技能注册表"""
    skills = SkillRegistry()
    skills.register(WebResearchSkill())
    skills.register(CodeSearchSkill())
    skills.register(DataAnalysisSkill())
    skills.register(HardwareCheckSkill())
    return skills


# ═══════════════════════════════════════════
# read_data 工具
# ═══════════════════════════════════════════

def test_read_csv_stats(fake_root):
    """CSV：列结构 + 数值列统计 + 类别列统计"""
    result = rd.read_data("sales.csv")
    assert "4 行 × 4 列" in result
    assert "[price] 数值列" in result
    assert "mean=" in result
    assert "[category] 类别列" in result
    assert "unique=3" in result  # fruit/vegetable/dairy
    assert "前 4 行预览" in result


def test_read_csv_numeric_detection(fake_root):
    """数值列应算出 min/max（价格 min=1.5, max=5.0）"""
    result = rd.read_data("sales.csv")
    assert "min=1.5" in result
    assert "max=5" in result


def test_read_json_array(fake_root):
    """JSON 数组按表分析"""
    result = rd.read_data("users.json")
    assert "3 条记录" in result
    assert "[age] 数值列" in result
    assert "[name] 类别列" in result


def test_read_json_object(fake_root):
    """JSON 对象展示顶层键"""
    result = rd.read_data("meta.json")
    assert "version" in result
    assert "features: list[2]" in result
    assert "count" in result


def test_read_jsonl(fake_root):
    """JSONL 逐行解析并统计"""
    result = rd.read_data("log.jsonl")
    assert "JSONL" in result
    assert "[ms] 数值列" in result
    assert "[level] 类别列" in result


def test_read_text(fake_root):
    """文本文件返回行数与预览"""
    (fake_root / "notes.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    result = rd.read_data("notes.txt")
    assert "共 3 行" in result
    assert "L1: line1" in result


def test_read_data_out_of_root(fake_root):
    """越界文件被拒绝"""
    outside = fake_root.parent / "secret.csv"
    outside.write_text("a,b\n1,2\n", encoding="utf-8")
    result = rd.read_data(str(outside))
    assert "不在项目目录内" in result


def test_read_data_not_found(fake_root):
    """文件不存在"""
    result = rd.read_data("nope.csv")
    assert "文件不存在" in result


def test_read_data_binary(fake_root):
    """二进制文件被拒绝"""
    result = rd.read_data("blob.bin")
    assert "二进制格式" in result


def test_read_data_unsupported_format(fake_root):
    """不支持的格式"""
    (fake_root / "data.xml").write_text("<a/>", encoding="utf-8")
    result = rd.read_data("data.xml")
    assert "不支持的数据格式" in result


def test_read_data_csv_bad_format(fake_root):
    """format 参数显式指定"""
    result = rd.read_data("sales.csv", format="csv", preview_rows=2)
    assert "前 2 行预览" in result


# ═══════════════════════════════════════════
# Router 匹配：data_analysis_visual
# ═══════════════════════════════════════════

def test_router_data_analysis_zh():
    """中文数据分析意图命中 data_analysis_visual"""
    reg = _build_registry()
    for intent in ["分析一下数据文件里的销售趋势", "这个表格数据统计一下", "看看数据概况", "csv数据里有什么"]:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == "data_analysis_visual", f"意图应命中 data: {intent}"


def test_router_data_analysis_en():
    """英文数据分析意图命中 data_analysis_visual"""
    reg = _build_registry()
    for intent in ["analyze data in sales.csv", "data analysis for the report", "look at the data"]:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == "data_analysis_visual", f"意图应命中 data: {intent}"


def test_router_no_conflict_four_skills():
    """四类意图各命中各的技能，互不抢占"""
    reg = _build_registry()
    cases = [
        ("帮我搜索一下 Python 异步框架的资料", "web_research_summarize"),
        ("搜索代码里处理异常的部分", "code_search_explore"),
        ("分析一下数据文件里的销售趋势", "data_analysis_visual"),
        ("检测硬件配置并判断 QLoRA 条件", "hardware_check"),
    ]
    for intent, expected in cases:
        skill = reg.match(intent)
        assert skill is not None, f"应命中技能: {intent}"
        assert skill.name == expected, f"{intent} 应命中 {expected}，实际 {skill.name}"


def test_router_code_not_stolen_by_data():
    """'分析一下代码' 应命中 code 而非 data（data 不使用宽泛'分析一下'）"""
    reg = _build_registry()
    skill = reg.match("分析一下代码里的主循环")
    assert skill is not None
    assert skill.name == "code_search_explore"


def test_router_no_match():
    """无关意图不命中任何技能"""
    reg = _build_registry()
    for intent in ["今天晚饭吃什么", "讲个笑话", "你好"]:
        assert reg.match(intent) is None, f"不应命中技能: {intent}"
