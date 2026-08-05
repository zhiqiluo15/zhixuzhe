"""工具注册表 —— 管理所有手脚的注册与调用"""

from typing import Callable


class Tool:
    """单个工具"""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters or {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def execute(self, **kwargs) -> str:
        try:
            return str(self.func(**kwargs))
        except Exception as e:
            return f"工具执行失败: {e}"

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
            return f"未知工具: {name}（可用工具: {', '.join(self._tools)})"
        return tool.execute(**kwargs)
