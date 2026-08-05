"""DeepSeek API 大脑 —— 通过云端 API 调用思考"""

import os
from pathlib import Path

import requests

from engine.brain.base import Brain, Message
from engine.utils import load_dotenv


class DeepSeekAPIBrain(Brain):
    """通过 DeepSeek API 调用的大脑后端。
    
    API Key 读取优先级：构造参数 > 项目根 .env 文件 > DEEPSEEK_API_KEY 环境变量。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
    ):
        root = Path(__file__).resolve().parent.parent.parent
        dotenv = load_dotenv(root)
        self.api_key = (
            api_key
            or dotenv.get("DEEPSEEK_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "未找到 DEEPSEEK_API_KEY。请任选一种方式设置：\n"
                "  1. 在项目根目录创建 .env 文件，写入 DEEPSEEK_API_KEY=你的key\n"
                "  2. 设置环境变量：$env:DEEPSEEK_API_KEY='你的key'\n"
                "  3. 代码传参：DeepSeekAPIBrain(api_key='你的key')\n"
                "获取 Key：https://platform.deepseek.com/api_keys"
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
