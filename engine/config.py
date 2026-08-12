"""智序者统一配置系统

从项目根 config.yaml 加载配置，支持环境变量覆盖（${env:VAR_NAME} 语法）。
所有模块通过 from engine.config import config 获取单例配置。

用法：
    from engine.config import config
    max_rounds = config.agent.max_tool_rounds
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 环境变量插值模式: ${env:VAR_NAME}
_ENV_PATTERN = re.compile(r"\$\{env:([^}]+)\}")


def _resolve_env(value: str) -> str:
    """解析字符串中的 ${env:VAR} 引用"""
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), "")
    return _ENV_PATTERN.sub(_replace, value)


def _resolve_dict(data: dict) -> dict:
    """递归解析 dict 中的环境变量引用"""
    result = {}
    for k, v in data.items():
        if isinstance(v, str):
            result[k] = _resolve_env(v)
        elif isinstance(v, dict):
            result[k] = _resolve_dict(v)
        elif isinstance(v, list):
            result[k] = [_resolve_env(x) if isinstance(x, str) else x for x in v]
        else:
            result[k] = v
    return result


# ── 微型 YAML 解析器（仅支持所需语法，零依赖） ──

def _parse_yaml(text: str) -> dict:
    """解析简化 YAML：支持 key: value、嵌套 dict、list（块状 `- item` 与内联 `[..]`）、# 注释。
    不处理多行字符串、引用、tag 等高级特性。
    """
    lines = text.splitlines()
    result: dict = {}
    stack: list[tuple[int, dict]] = [(0, result)]  # (indent, target_dict)
    # 记录最近一个"空值 key"，用于承接其下缩进的块状列表项 - (key, key_indent, parent)
    pending_list: tuple[str, int, dict] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # 块状列表项: - value 或单独的 -
        if stripped.startswith("-"):
            item_str = stripped[1:].strip().strip('"').strip("'")
            item = item_str if item_str == "" else _parse_value(item_str)

            # 若该项缩进比最近空值 key 更深，则归入该 key 的列表
            if pending_list and indent > pending_list[1]:
                key, _, parent = pending_list
                # 若当前是空 dict（key: 后无子键），先转为列表
                if isinstance(parent.get(key), dict) and not parent[key]:
                    parent[key] = []
                parent[key].append(item)
            continue

        # key: value
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            # 去除行内注释 (e.g. "5  # comment")
            if "#" in val:
                val = val.split("#")[0].strip()

            # 回退栈到合适的缩进级别
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if not stack:
                # 顶层
                current = result
            else:
                current = stack[-1][1]

            if val == "":
                # 嵌套 dict（也可能是块状列表，由后续 - item 决定）
                nested: dict = {}
                current[key] = nested
                stack.append((indent, nested))
                pending_list = (key, indent, current)
            elif val.startswith("[") and val.endswith("]"):
                # 内联列表值
                items = val[1:-1].split(",")
                current[key] = [
                    _parse_value(i.strip().strip('"').strip("'")) for i in items if i.strip()
                ]
                pending_list = None
            else:
                val = val.strip('"').strip("'")
                current[key] = _parse_value(val)
                pending_list = None

    return result


def _parse_value(val: str):
    """解析 YAML 值为 Python 类型"""
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.lower() in ("null", "~", "none"):
        return None
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val


# ── 配置数据类 ──

@dataclass
class ModelConfig:
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.4
    max_tokens: int = 16384
    request_timeout: int = 60
    max_retries: int = 3


@dataclass
class ContextConfig:
    """上下文压缩配置（长对话自动摘要，控制输入 token 成本）"""
    enabled: bool = True
    keep_recent: int = 20       # 保留最近完整消息条数（对话连续性）
    summarize_chunk: int = 10   # 累计新增多少条旧消息触发一次摘要
    max_summary_chars: int = 1500  # 摘要文本上限（超出截断）


@dataclass
class AgentConfig:
    max_tool_rounds: int = 10
    max_tool_output_chars: int = 32000
    confirm_tools: list[str] = field(default_factory=lambda: ["run_shell"])
    auto_task: bool = True
    context: ContextConfig = field(default_factory=ContextConfig)


@dataclass
class TaskConfig:
    max_steps: int = 8
    plan_retries: int = 3
    max_tool_rounds: int = 15


@dataclass
class MemoryConfig:
    min_score: float = 0.25
    max_entries: int = 3
    entry_max_chars: int = 300
    dedup_threshold: float = 0.7


@dataclass
class LoggingConfig:
    level: str = "INFO"
    dir: str = "logs"
    file_max_bytes: int = 10 * 1024 * 1024
    file_backup_count: int = 5
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


@dataclass
class ShellToolConfig:
    default_timeout: int = 30
    max_timeout: int = 120
    max_retries: int = 2


@dataclass
class FileToolConfig:
    max_file_size: int = 1 * 1024 * 1024
    allowed_dirs: list[str] = field(default_factory=list)


@dataclass
class ToolsConfig:
    shell: ShellToolConfig = field(default_factory=ShellToolConfig)
    file: FileToolConfig = field(default_factory=FileToolConfig)


@dataclass
class LearningConfig:
    repo_dir: str = "memory/knowledge/repos"
    knowledge_dir: str = "memory/knowledge/languages"
    max_repo_size_mb: int = 200
    max_repo_depth: int = 1
    max_source_files: int = 5


@dataclass
class Config:
    """智序者全局配置"""
    model: ModelConfig = field(default_factory=ModelConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)


def load_config(path: Path | str | None = None) -> Config:
    """从 YAML 文件加载配置，返回 Config 实例。

    Args:
        path: 配置文件路径（Path 或 str），默认项目根 config.yaml

    Returns:
        Config 实例，文件不存在时返回默认配置
    """
    if path is None:
        path = _PROJECT_ROOT / "config.yaml"
    elif isinstance(path, str):
        path = Path(path)

    cfg = Config()

    if not path.exists():
        return cfg

    raw = path.read_text(encoding="utf-8")
    data = _resolve_dict(_parse_yaml(raw))

    # 逐层合并
    if "model" in data:
        cfg.model = ModelConfig(**{
            k: v for k, v in data["model"].items()
            if k in ModelConfig.__dataclass_fields__
        })

    if "agent" in data:
        agent_kwargs = {
            k: v for k, v in data["agent"].items()
            if k in AgentConfig.__dataclass_fields__ and k != "context"
        }
        cfg.agent = AgentConfig(**agent_kwargs)
        if "context" in data["agent"]:
            cfg.agent.context = ContextConfig(**{
                k: v for k, v in data["agent"]["context"].items()
                if k in ContextConfig.__dataclass_fields__
            })

    if "task" in data:
        cfg.task = TaskConfig(**{
            k: v for k, v in data["task"].items()
            if k in TaskConfig.__dataclass_fields__
        })

    if "memory" in data:
        cfg.memory = MemoryConfig(**{
            k: v for k, v in data["memory"].items()
            if k in MemoryConfig.__dataclass_fields__
        })

    if "logging" in data:
        cfg.logging = LoggingConfig(**{
            k: v for k, v in data["logging"].items()
            if k in LoggingConfig.__dataclass_fields__
        })

    if "tools" in data:
        tools_data = data["tools"]
        if "shell" in tools_data:
            cfg.tools.shell = ShellToolConfig(**{
                k: v for k, v in tools_data["shell"].items()
                if k in ShellToolConfig.__dataclass_fields__
            })
        if "file" in tools_data:
            cfg.tools.file = FileToolConfig(**{
                k: v for k, v in tools_data["file"].items()
                if k in FileToolConfig.__dataclass_fields__
            })

    if "learning" in data:
        cfg.learning = LearningConfig(**{
            k: v for k, v in data["learning"].items()
            if k in LearningConfig.__dataclass_fields__
        })

    return cfg


# 全局单例
config = load_config()
