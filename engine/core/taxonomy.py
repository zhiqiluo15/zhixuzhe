"""知识分类树管理器 —— 提供知识分类数据的加载与查询

知识分类树定义了智序者可以学习的全部计算机知识主题。
每个叶子节点包含搜索提示词、难度等级、所属语言/领域。
前端通过 API 获取树结构渲染卡片，后端用节点信息驱动学习任务。

分类数据来源于 engine/knowledge/taxonomy.yaml（可读参考），
由本模块的 _BUILTIN_TAXONOMY 内置数据结构加载。
新增主题时同时更新 taxonomy.yaml 和本文件的内置数据。
"""

from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class KnowledgeNode:
    """知识分类树叶子节点"""
    id: str
    name: str
    parent: str              # 所属语言/领域
    search: str              # GitHub 搜索提示词
    repo_hint: str = ""
    difficulty: str = "intermediate"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent": self.parent,
            "difficulty": self.difficulty,
        }


@dataclass
class Category:
    """知识分类（顶层分组）"""
    id: str
    name: str
    icon: str
    children: list[KnowledgeNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "children": [c.to_dict() for c in self.children],
        }


# ══════════════════════════════════════
#  内置知识分类数据（与 taxonomy.yaml 同步维护）
# ══════════════════════════════════════

_BUILTIN_TAXONOMY: list[Category] = [
    Category("programming-languages", "编程语言", "code", [
        KnowledgeNode("async-python", "异步编程", "Python",
            "python asyncio best practices production patterns",
            "python/cpython/tree/main/Lib/asyncio", "intermediate"),
        KnowledgeNode("typing-python", "类型系统", "Python",
            "python typing best practices mypy pydantic type hints",
            "", "intermediate"),
        KnowledgeNode("concurrency-python", "并发模型", "Python",
            "python concurrency threading multiprocessing GIL best practices",
            "", "advanced"),
        KnowledgeNode("web-frameworks-python", "Web 框架", "Python",
            "python FastAPI Django best practices production architecture",
            "", "intermediate"),
        KnowledgeNode("data-processing-python", "数据处理", "Python",
            "python pandas polars numpy data processing best practices",
            "", "intermediate"),
        KnowledgeNode("performance-python", "性能优化", "Python",
            "python performance optimization profiling Cython memory best practices",
            "", "advanced"),
        KnowledgeNode("packaging-python", "包管理", "Python",
            "python pip poetry uv packaging best practices",
            "", "beginner"),
        KnowledgeNode("testing-python", "测试", "Python",
            "python pytest testing best practices mock fixtures patterns",
            "", "beginner"),
    ]),
    Category("systems-languages", "系统编程语言", "cpu", [
        KnowledgeNode("rust-ownership", "所有权与借用", "Rust",
            "rust ownership borrowing patterns best practices",
            "", "intermediate"),
        KnowledgeNode("rust-error-handling", "错误处理", "Rust",
            "rust error handling Result anyhow thiserror best practices",
            "", "intermediate"),
        KnowledgeNode("rust-async", "异步运行时", "Rust",
            "rust tokio async runtime patterns best practices",
            "", "advanced"),
        KnowledgeNode("rust-concurrency", "并发安全", "Rust",
            "rust Send Sync Arc concurrency patterns best practices",
            "", "advanced"),
        KnowledgeNode("go-concurrency", "Go 并发模型", "Go",
            "go goroutine channel concurrency patterns best practices",
            "", "intermediate"),
        KnowledgeNode("c-performance", "C 性能优化", "C",
            "C performance optimization memory layout SIMD best practices",
            "", "advanced"),
    ]),
    Category("system-design", "系统设计", "architecture", [
        KnowledgeNode("distributed-consensus", "分布式一致性", "系统设计",
            "distributed consensus RAFT Paxos implementation best practices",
            "", "advanced"),
        KnowledgeNode("message-queue", "消息队列", "系统设计",
            "message queue Kafka NATS RabbitMQ best practices production",
            "", "intermediate"),
        KnowledgeNode("database-design", "数据库设计", "系统设计",
            "database index SQL optimization transaction design best practices",
            "", "intermediate"),
        KnowledgeNode("microservices", "微服务", "系统设计",
            "microservices service discovery gateway circuit breaker best practices",
            "", "advanced"),
        KnowledgeNode("api-design", "API 设计", "系统设计",
            "REST gRPC GraphQL API design best practices patterns",
            "", "intermediate"),
        KnowledgeNode("caching", "缓存策略", "系统设计",
            "Redis cache strategy multi-level caching best practices",
            "", "intermediate"),
    ]),
    Category("ai-ml", "AI / 机器学习", "brain", [
        KnowledgeNode("model-finetuning", "模型微调", "AI/ML",
            "QLoRA SFT model fine-tuning data engineering best practices",
            "", "advanced"),
        KnowledgeNode("inference-optimization", "推理优化", "AI/ML",
            "vLLM inference optimization quantization model serving best practices",
            "", "advanced"),
        KnowledgeNode("rag-systems", "RAG 系统", "AI/ML",
            "RAG retrieval augmented generation chunking rerank best practices",
            "", "intermediate"),
        KnowledgeNode("agent-architecture", "Agent 架构", "AI/ML",
            "AI agent ReAct tool-use planning architecture best practices",
            "", "advanced"),
        KnowledgeNode("vector-retrieval", "向量检索", "AI/ML",
            "vector embedding ANN hybrid retrieval best practices",
            "", "intermediate"),
    ]),
    Category("low-level-systems", "底层系统", "chip", [
        KnowledgeNode("os-internals", "操作系统", "底层系统",
            "operating system process scheduling memory management internals",
            "", "advanced"),
        KnowledgeNode("network-protocols", "网络协议栈", "底层系统",
            "TCP IP HTTP2 QUIC network protocol implementation best practices",
            "", "advanced"),
        KnowledgeNode("compiler", "编译原理", "底层系统",
            "LLVM JIT bytecode compiler implementation best practices",
            "", "advanced"),
        KnowledgeNode("filesystem", "文件系统", "底层系统",
            "B-tree LSM log-structured filesystem implementation",
            "", "advanced"),
    ]),
    Category("engineering-practice", "工程实践", "tools", [
        KnowledgeNode("design-patterns", "设计模式", "工程实践",
            "design patterns GoF functional dependency injection best practices",
            "", "intermediate"),
        KnowledgeNode("cicd", "CI/CD", "工程实践",
            "CI CD GitHub Actions deployment strategy best practices",
            "", "beginner"),
        KnowledgeNode("containerization", "容器化", "工程实践",
            "Docker Kubernetes orchestration best practices production",
            "", "intermediate"),
        KnowledgeNode("testing-strategy", "测试策略", "工程实践",
            "TDD integration testing e2e testing strategy best practices",
            "", "intermediate"),
        KnowledgeNode("code-review", "代码审查", "工程实践",
            "code review checklist static analysis best practices patterns",
            "", "beginner"),
    ]),
    Category("security", "安全", "shield", [
        KnowledgeNode("web-security", "Web 安全", "安全",
            "web security XSS CSRF SQLi SSRF OWASP defense best practices",
            "shieldfy/API-Security-Checklist", "intermediate"),
        KnowledgeNode("auth", "认证授权", "安全",
            "OAuth2 JWT RBAC authentication authorization best practices",
            "", "intermediate"),
        KnowledgeNode("cryptography", "密码学", "安全",
            "TLS hash signature cryptography implementation best practices",
            "", "advanced"),
        KnowledgeNode("vulnerability", "逆向与漏洞", "安全",
            "fuzzing symbolic execution vulnerability research best practices",
            "", "advanced"),
    ]),
]

_LEARNING_CONFIG = {
    "repo_dir": "memory/knowledge/repos",
    "knowledge_dir": "memory/knowledge/languages",
    "max_repo_size_mb": 200,
}


class TaxonomyManager:
    """知识分类树管理器

    负责加载和查询知识分类树，提供节点查找和学习任务生成。
    与 ProfileManager 配合：学习完成后按节点 parent 更新能力档案。
    """

    def __init__(self, root: Path):
        self.root = root
        self.categories: list[Category] = []
        self._node_index: dict[str, KnowledgeNode] = {}
        self.learning_config = _LEARNING_CONFIG

    def load(self) -> None:
        """加载内置知识分类数据"""
        if self._node_index:
            return  # 已加载

        self.categories = list(_BUILTIN_TAXONOMY)
        for cat in self.categories:
            for node in cat.children:
                self._node_index[node.id] = node

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        self.load()
        return self._node_index.get(node_id)

    def search_parents(self) -> set[str]:
        self.load()
        return {n.parent for c in self.categories for n in c.children}

    def max_topics_for_parent(self, parent: str) -> int:
        self.load()
        return sum(1 for n in self._node_index.values() if n.parent == parent)

    def to_dict(self) -> list[dict]:
        self.load()
        return [c.to_dict() for c in self.categories]

    def generate_search_query(self, node_id: str) -> str:
        node = self.get_node(node_id)
        if not node:
            return ""
        return f"{node.search} site:github.com"
