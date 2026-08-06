"""大脑基类 —— 所有大脑后端的抽象接口"""

from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass


@dataclass
class Message:
    """一条对话消息"""
    role: str               # system / user / assistant / tool
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict:
        """序列化为 OpenAI API 兼容字典"""
        d: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


class Brain(ABC):
    """大脑抽象基类。所有后端（API / 本地模型）实现此接口。"""

    @abstractmethod
    def think(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        """思考：接收对话消息，返回一条 assistant 消息。"""
        ...

    def think_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Generator[tuple[str, object], None, None]:
        """流式思考：逐 chunk 产出，而非一次性返回。

        产出元组：
        - ("text", str)       文本块，可实时显示
        - ("done", Message)   最终完整 Message（含 tool_calls 若有）

        默认实现：回退到 think()，一次性产出全部文本后 done。
        子类可覆写实现真正的 SSE 流式。
        """
        result = self.think(messages, tools)
        if result.content:
            yield ("text", result.content)
        yield ("done", result)
