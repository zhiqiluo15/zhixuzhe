"""DeepSeek API 大脑 —— 通过云端 API 调用思考"""

import os
import time
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
        model: str = "deepseek-v4-pro",
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
        """调用 DeepSeek API，带自动重试（最多 3 次）。

        可重试：429（限流）、5xx（服务端错误）、网络超时/连接错误。
        不可重试：4xx 非 429（如 401 认证失败、400 参数错误），直接抛出。
        3 次全败后返回含错误信息的 Message，不会崩溃。
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
        }
        if tools:
            payload["tools"] = tools

        last_error = ""
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )

                if resp.ok:
                    data = resp.json()
                    choice = data["choices"][0]["message"]
                    return Message(
                        role="assistant",
                        content=choice.get("content") or "",
                        tool_calls=choice.get("tool_calls"),
                    )

                # 429 限流 / 5xx 服务端错误 → 可重试
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                else:
                    # 4xx 非 429（401/400 等）→ 不重试，直接抛
                    resp.raise_for_status()

            except requests.RequestException as e:
                last_error = str(e)[:200]

            # 指数退避：1s, 2s（最后一次不等待）
            if attempt < 2:
                time.sleep(2 ** attempt)

        # 3 次全败，返回错误消息而非崩溃
        return Message(
            role="assistant",
            content=f"[API 调用失败（重试 3 次后）] {last_error}",
        )
