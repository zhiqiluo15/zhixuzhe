"""DeepSeek API 大脑 —— 通过云端 API 调用思考"""

import os

import requests

from engine.brain.base import Brain, Message


class DeepSeekAPIBrain(Brain):
    """通过 DeepSeek API 调用的大脑后端"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "未设置 DEEPSEEK_API_KEY 环境变量。\n"
                "请在 https://platform.deepseek.com/api_keys 获取 API Key，"
                "然后设置：$env:DEEPSEEK_API_KEY='你的key'"
            )
        self.model = model
        self.base_url = base_url.rstrip("/")

    def think(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict = {
            "model": self.model,
            "messages": [self._serialize(m) for m in messages],
        }
        if tools:
            payload["tools"] = tools

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]["message"]
        return Message(
            role="assistant",
            content=choice.get("content") or "",
            tool_calls=choice.get("tool_calls"),
        )

    def _serialize(self, msg: Message) -> dict:
        d: dict = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            d["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        return d
