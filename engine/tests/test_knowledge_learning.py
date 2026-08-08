"""知识学习成功判定测试 —— is_learning_failed（方案B：材料门槛 + 半数规则）"""

from engine.skills.knowledge_learning.skill import (
    FAILED_STEP_MARK,
    is_learning_failed,
)

FAIL = FAILED_STEP_MARK  # 步骤失败标记
OK = "步骤执行成功输出"


def test_all_steps_success():
    """5步全部成功 → 不失败"""
    assert not is_learning_failed([OK] * 5)


def test_material_steps_both_fail_is_failed():
    """材料步骤（搜索+克隆）全失败，即使后3步成功也判定失败（无材料来源）"""
    assert is_learning_failed([FAIL, FAIL, OK, OK, OK])


def test_material_step1_fail_step2_ok_is_success():
    """搜索失败但克隆成功（有仓库提示）→ 材料门槛通过，整体成功"""
    assert not is_learning_failed([FAIL, OK, OK, OK, OK])


def test_readme_fallback_partial_failure_is_success():
    """材料通过但探索/读码失败（README降级学习）：失败数2 未过半 → 不失败"""
    assert not is_learning_failed([OK, OK, FAIL, FAIL, OK])


def test_exact_half_failures_is_success():
    """失败数恰好半数（2 == 5//2）→ 未过半 → 成功"""
    assert not is_learning_failed([OK, OK, OK, FAIL, FAIL])


def test_more_than_half_failures_is_failed():
    """失败数3 > 5//2 → 失败"""
    assert is_learning_failed([OK, OK, FAIL, FAIL, FAIL])


def test_three_of_five_fail_with_material_ok_is_failed():
    """材料通过但3步失败 → 超过半数 → 失败（旧阈值 len-1=4 会误判为成功）"""
    assert is_learning_failed([OK, FAIL, FAIL, FAIL, OK])


def test_empty_results_is_failed():
    """无任何步骤结果 → 失败（退化场景安全兜底）"""
    assert is_learning_failed([])
