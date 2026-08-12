"""语义检索索引 —— 向量嵌入 + 余弦检索，与关键词检索 RRF 融合

补齐 v1.2 关键词检索（2-gram）的语义盲区：同义改写、概念相关（如"训练模型"与
"微调权重"）此前无法命中。

设计原则：
- 可选增强，绝不阻断：嵌入模型懒加载（首次检索才加载）；模型缺失/下载失败/
  依赖未装 → 自动降级纯关键词检索，用户无感知
- 增量缓存：条目向量持久化到 .runtime/memory_semantic.json（含内容 hash），
  仅对变更条目重新嵌入；缓存目录在 .gitignore 内，不会推送到 GitHub
- RRF 融合：关键词 top-k 与语义 top-k 按排名融合（1/(k+rank)），规避两套
  分数量纲不一致的调参难题；语义层不可用时跳过融合直接按关键词排序

嵌入器接口：提供 encode(texts) -> np.ndarray（每行一个归一化向量）。
默认实现加载 sentence-transformers 的 BGE 中文检索模型；测试可注入 FakeEmbedder。
"""

import hashlib
import json
from pathlib import Path

import numpy as np

from engine.log import get_logger

logger = get_logger(__name__)

# 语义索引覆盖的来源目录（与 MemoryReader 保持一致）
_SOURCE_DIRS = {
    "diary": "memory/diary",
    "experience": "memory/experience",
    "knowledge": "memory/knowledge/languages",
}


# ── RRF 融合 ──

def _rrf_fuse(ranked_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion：将多路按相关度排序的结果按排名融合。

    每路排名越靠前的条目获得越高贡献（1/(k+rank+1)），同一条目出现在多路中
    时分数累加。返回按融合分降序的条目列表（条目为 {source, date, content, ...}）。
    """
    acc: dict[tuple, dict] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            key = (item.get("source"), item.get("date"), item.get("content"))
            if key not in acc:
                acc[key] = dict(item)
                acc[key]["_rrf"] = 0.0
            acc[key]["_rrf"] += 1.0 / (k + rank + 1)

    merged = sorted(acc.values(), key=lambda x: x["_rrf"], reverse=True)
    for m in merged:
        m["score"] = round(m.pop("_rrf"), 3)
    return merged


# ── 语义索引 ──

class SemanticIndex:
    """向量索引：扫描记忆目录 → 增量嵌入 → 余弦检索。

    key = "{source}:{file}:{idx}"，idx 为条目在文件内的序号（解析顺序稳定）。
    缓存文件损坏时自动重建，不阻断检索。
    """

    def __init__(
        self,
        root: Path,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        cache_path: Path | None = None,
        enabled: bool = True,
        min_similarity: float = 0.2,
        top_k_per_source: int = 10,
        embedder=None,
    ):
        self.root = root
        self.model_name = model_name
        self.cache_path = cache_path or (root / ".runtime" / "memory_semantic.json")
        self.enabled = enabled
        self.min_similarity = min_similarity
        self.top_k = top_k_per_source
        self._embedder = embedder          # 外部注入（测试用）；None 则懒加载真实模型
        self._model_error: str | None = None  # 非 None 表示加载失败，不再重试
        self._cache: dict[str, dict] = {}
        self._load_cache()

    # ── 可用性与模型加载 ──

    @property
    def available(self) -> bool:
        """语义层是否可用（依赖齐全且模型加载成功）"""
        if not self.enabled:
            return False
        self._ensure_model()
        return self._embedder is not None

    def _ensure_model(self) -> bool:
        """懒加载嵌入模型；失败记录错误并降级，不重试"""
        if self._embedder is not None or self._model_error is not None:
            return self._embedder is not None
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"语义检索模型加载中: {self.model_name}（首次使用自动下载，约 100MB）")
            self._embedder = SentenceTransformer(self.model_name)
            logger.info(f"语义检索模型已加载: {self.model_name}")
        except Exception as e:
            self._model_error = str(e)
            logger.warning(
                f"语义检索模型加载失败，已降级为纯关键词检索（不影响使用）: {e}。"
                f"可执行 pip install sentence-transformers，并设置 HF_ENDPOINT=https://hf-mirror.com 加速下载"
            )
        return self._embedder is not None

    # ── 扫描与增量更新 ──

    def scan_and_update(self) -> bool:
        """扫描三个来源目录，增量嵌入变更条目；返回语义层是否可用"""
        if not self.enabled:
            return False
        if not self._ensure_model():
            return False
        entries = self._collect_entries()
        if not entries and self._cache:
            # 记忆目录为空（reset），清空缓存
            self._cache = {}
            self._save_cache()
            return True

        valid_keys = set()
        pending: list[tuple[str, str, str, dict]] = []
        for e in entries:
            key = f"{e['source']}:{e['file']}:{e['idx']}"
            valid_keys.add(key)
            text = f"{e['title']}\n{e['body']}"
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
            cached = self._cache.get(key)
            if cached and cached.get("hash") == h:
                continue
            pending.append((key, text, h, e))

        if pending:
            vectors = self._encode_texts([p[1] for p in pending])
            for (key, text, h, e), vec in zip(pending, vectors):
                self._cache[key] = {
                    "hash": h,
                    "vector": vec.tolist(),
                    "source": e["source"],
                    "date": e["date"],
                    "file": e["file"],
                    "idx": e["idx"],
                    "text_display": text[:500],  # 展示/融合用，与关键词层 content 格式一致
                }
            logger.info(f"语义索引增量更新: {len(pending)} 条新/变更条目")

        # 清理已删除条目的缓存
        stale = [k for k in self._cache if k not in valid_keys]
        if stale:
            for k in stale:
                del self._cache[k]
            logger.debug(f"语义索引清理: 移除 {len(stale)} 条已删除条目")

        if pending or stale:
            self._save_cache()
        return True

    def _collect_entries(self) -> list[dict]:
        """扫描目录解析条目，携带 source/date/file/idx 定位信息"""
        # 局部导入避免与 memory_reader 循环依赖（semantic 与 memory_reader 相互引用）
        from engine.core.memory_reader import (
            _parse_diary_entries,
            _extract_date,
            _extract_date_from_header,
        )

        entries: list[dict] = []
        for source, rel_dir in _SOURCE_DIRS.items():
            directory = self.root / rel_dir
            if not directory.exists():
                continue
            pattern = "**/*.md" if source == "knowledge" else "*.md"
            for md_file in sorted(directory.glob(pattern), reverse=True):
                try:
                    content = md_file.read_text(encoding="utf-8")
                except Exception:
                    continue
                date_str = _extract_date(md_file.name)
                if source == "knowledge" and not date_str:
                    date_str = _extract_date_from_header(content)
                for idx, entry in enumerate(_parse_diary_entries(content)):
                    entries.append({
                        "source": source,
                        "date": date_str,
                        "file": md_file.name,
                        "idx": idx,
                        "title": entry["title"],
                        "body": entry["body"],
                    })
        return entries

    # ── 检索 ──

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """余弦检索，返回按相似度降序的条目列表（content 与关键词层格式一致）"""
        if not self.enabled or not self._ensure_model() or not self._cache or not query.strip():
            return []
        qv = self._encode_texts([query])[0]
        top_k = top_k or self.top_k

        scored: list[dict] = []
        for item in self._cache.values():
            sim = float(np.dot(qv, np.array(item["vector"])))  # 向量均已归一化
            if sim < self.min_similarity:
                continue
            scored.append({
                "source": item["source"],
                "date": item["date"],
                "content": item.get("text_display", ""),
                "score": round(sim, 3),
            })
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    # ── 嵌入与缓存 ──

    def _encode_texts(self, texts: list[str]) -> np.ndarray:
        """编码文本为归一化向量矩阵（嵌入器接口统一为 encode）"""
        if not texts:
            return np.zeros((0, 8), dtype=np.float32)
        return np.asarray(self._embedder.encode(texts), dtype=np.float32)

    def _load_cache(self) -> None:
        """从缓存文件加载向量索引；文件损坏/缺失时重建空索引"""
        try:
            if self.cache_path.exists():
                raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._cache = {k: v for k, v in raw.items() if isinstance(v, dict)}
        except Exception as e:
            logger.warning(f"语义索引缓存读取失败，将重建: {e}")
            self._cache = {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._cache, ensure_ascii=False), encoding="utf-8",
            )
            tmp.replace(self.cache_path)
        except Exception as e:
            logger.warning(f"语义索引缓存保存失败（不影响本次检索）: {e}")
