"""语义检索层测试

验证 RRF 融合、增量索引（不重嵌入）、缓存持久化、语义命中（无共同字符）、
降级路径（禁用/加载失败 → 纯关键词）。用 FakeEmbedder 模拟嵌入，不依赖真实模型。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pytest

from engine.core.memory_reader import MemoryReader
from engine.core.semantic import SemanticIndex, _rrf_fuse


class FakeEmbedder:
    """伪嵌入器：按主题词典做"语义桶"，验证无共同字符的语义命中

    主题 0：模型训练（QLoRA/LoRA/训练/微调）；主题 1：视频制作（视频/配音/剪辑/音乐）
    文本命中某主题词 → 归入该主题桶；无命中归入主题 2（其他）。
    """

    THEMES = {
        "QLoRA": 0, "LoRA": 0, "训练": 0, "微调": 0,
        "视频": 1, "配音": 1, "剪辑": 1, "音乐": 1,
    }

    def __init__(self):
        self.encode_calls = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.encode_calls += 1
        vecs = []
        for t in texts:
            v = np.zeros(3)
            for word, idx in self.THEMES.items():
                if word.lower() in t.lower():
                    v[idx] += 1.0
            if v.sum() == 0:
                v[2] = 1.0
            v = v / (np.linalg.norm(v) + 1e-9)
            vecs.append(v)
        return np.array(vecs, dtype=np.float32)


def _write_diary(root: Path, filename: str, body: str) -> None:
    d = root / "memory" / "diary"
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(
        f"# 日记\n\n## 10:00:00\n{body}\n", encoding="utf-8",
    )


def _make_index(root: Path, **kw) -> SemanticIndex:
    kw.setdefault("enabled", True)
    kw.setdefault("embedder", FakeEmbedder())
    kw.setdefault("min_similarity", 0.2)
    return SemanticIndex(root=root, **kw)


# ── RRF 融合 ──

def test_rrf_fuse_ranks_overlap_first():
    """同一条目出现在两路时分数累加，排在最前"""
    kw = [
        {"source": "diary", "date": "2026-08-01", "content": "A", "score": 0.8},
        {"source": "diary", "date": "2026-08-02", "content": "B", "score": 0.6},
    ]
    sem = [
        {"source": "experience", "date": "", "content": "C", "score": 0.9},
        {"source": "diary", "date": "2026-08-01", "content": "A", "score": 0.7},
    ]
    fused = _rrf_fuse([kw, sem], k=60)

    assert len(fused) == 3
    assert fused[0]["content"] == "A", "两路都出现的条目应排第一"
    assert fused[0]["score"] == round(2 / 61, 3)  # rank0×2
    assert fused[1]["content"] == "C"
    assert fused[2]["content"] == "B"
    assert "score" in fused[0] and "_rrf" not in fused[0]


# ── 增量索引 ──

def test_incremental_update_skips_unchanged(tmp_path: Path):
    """无变更时第二次扫描不重新嵌入"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si = _make_index(tmp_path)

    assert si.scan_and_update() is True
    calls_after_first = si._embedder.encode_calls

    assert si.scan_and_update() is True
    assert si._embedder.encode_calls == calls_after_first, "无变更不应重新嵌入"


def test_incremental_update_embeds_only_changed(tmp_path: Path):
    """新增条目只嵌入新增部分"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si = _make_index(tmp_path)
    si.scan_and_update()
    baseline = si._embedder.encode_calls

    _write_diary(tmp_path, "20260802.md", "剪辑视频添加配音")
    si.scan_and_update()
    assert si._embedder.encode_calls == baseline + 1, "新增 1 条 → 1 次批量嵌入"


def test_cache_persistence(tmp_path: Path):
    """向量缓存持久化：重建实例后不重新嵌入"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si1 = _make_index(tmp_path)
    si1.scan_and_update()
    assert si1._cache, "首次扫描应建立索引"

    si2 = SemanticIndex(
        root=tmp_path,
        enabled=True,
        embedder=FakeEmbedder(),
        cache_path=si1.cache_path,
    )
    assert si2.scan_and_update() is True
    assert si2._embedder.encode_calls == 0, "从缓存加载，不应重新嵌入"


# ── 语义命中 ──

def test_search_semantic_hit_without_common_chars(tmp_path: Path):
    """语义命中：query 与条目无共同字符（微调 vs 训练）"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si = _make_index(tmp_path)
    si.scan_and_update()

    res = si.search("微调")

    assert res, "应命中语义相关的训练条目"
    assert "训练" in res[0]["content"]
    assert res[0]["score"] >= 0.99


def test_search_filters_below_min_similarity(tmp_path: Path):
    """低于 min_similarity 的条目被过滤"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si = _make_index(tmp_path, min_similarity=0.99)
    si.scan_and_update()

    assert si.search("剪辑视频") == [], "不同主题桶余弦为 0，低于阈值"


# ── 降级路径 ──

def test_disabled_index_returns_nothing(tmp_path: Path):
    """enabled=False：扫描与检索都不执行"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si = SemanticIndex(root=tmp_path, enabled=False, embedder=FakeEmbedder())

    assert si.available is False
    assert si.scan_and_update() is False
    assert si.search("训练") == []


def test_model_load_failure_degrades(tmp_path: Path):
    """模型加载失败：记录错误后不再尝试，检索返回空（不阻断）"""
    _write_diary(tmp_path, "20260801.md", "用 LoRA 训练模型权重")
    si = SemanticIndex(root=tmp_path, enabled=True, embedder=None)
    si._model_error = "模拟模型加载失败"

    assert si.available is False
    assert si.scan_and_update() is False
    assert si.search("训练") == []


# ── MemoryReader 集成 ──

def test_reader_fusion_with_semantic(root: Path):
    """语义层启用：无共同字符的 query 也能命中相关经验（RRF 融合）"""
    reader = MemoryReader(root=root)
    reader.semantic.enabled = True
    reader.semantic._embedder = FakeEmbedder()

    # "训练" 与 QLoRA 经验（含"微调"）属同一主题桶，但关键词层 2-gram 无法命中
    results = reader.retrieve("训练", max_entries=3)

    assert any("OOM" in r["content"] for r in results), \
        "语义层应命中 QLoRA 微调经验（主题相关，无共同字符）"


def test_reader_degrades_to_keyword_without_semantic(root: Path):
    """语义层不可用：同 query 不命中纯语义相关条目，退化为关键词行为"""
    reader = MemoryReader(root=root)
    reader.semantic.enabled = False

    results = reader.retrieve("训练", max_entries=3)

    assert all("OOM" not in r["content"] for r in results), \
        "禁用语义层后不应命中无共同字符的条目"
