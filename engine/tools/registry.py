"""工具注册表 —— 管理所有手脚的注册与调用"""

import time
from typing import Callable

from engine.log import get_logger

logger = get_logger(__name__)


class Tool:
    """单个工具（支持自动重试）"""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict | None = None,
        max_retries: int = 0,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters or {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.max_retries = max_retries  # 0 = 不重试，最多 3 次

    def execute(self, **kwargs) -> str:
        last_error = None
        attempts = self.max_retries + 1
        _t0 = time.perf_counter()
        for attempt in range(attempts):
            try:
                result = str(self.func(**kwargs))
                elapsed_ms = (time.perf_counter() - _t0) * 1000
                logger.debug(f"工具执行成功: {self.name} 耗时={elapsed_ms:.0f}ms")
                return result
            except Exception as e:
                last_error = e
                # exc_info=True 记录完整堆栈，方便排查工具内部错误
                logger.error(
                    f"工具执行失败: {self.name} 第{attempt + 1}次尝试 "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )
                if attempt < self.max_retries:
                    wait = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                    time.sleep(wait)
        return (
            f"工具执行失败（已重试 {self.max_retries} 次）: {last_error}"
        )

    def to_openai_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def to_openai_specs(self) -> list[dict]:
        return [t.to_openai_spec() for t in self._tools.values()]

    def execute(self, name: str, **kwargs) -> str:
        tool = self._tools.get(name)
        if tool is None:
            logger.warning(f"调用未知工具: {name}（可用: {', '.join(self._tools)}）")
            return f"未知工具: {name}（可用工具: {', '.join(self._tools)})"
        return tool.execute(**kwargs)

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools)
