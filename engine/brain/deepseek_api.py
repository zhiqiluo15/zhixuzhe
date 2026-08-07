"""DeepSeek API 大脑 —— 通过云端 API 调用思考"""

import json
import os
import time
from collections.abc import Generator
from pathlib import Path

import requests

from engine.brain.base import Brain, Message
from engine.utils import load_dotenv
from engine.config import config
from engine.log import get_logger

logger = get_logger(__name__)


class DeepSeekAPIBrain(Brain):
    """通过 DeepSeek API 调用的大脑后端。
    
    API Key 读取优先级：构造参数 > 项目根 .env 文件 > DEEPSEEK_API_KEY 环境变量。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
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
        self.model = model or config.model.model
        self.base_url = (base_url or config.model.base_url).rstrip("/")

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
            "temperature": config.model.temperature,
            "max_tokens": config.model.max_tokens,
        }
        if tools:
            payload["tools"] = tools

        last_error = ""
        for attempt in range(config.model.max_retries):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=config.model.request_timeout,
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
                    # 4xx 非 429（401/400 等）→ 不重试，直接返回错误
                    logger.error(f"API 不可重试错误 HTTP {resp.status_code}: {resp.text[:200]}")
                    return Message(
                        role="assistant",
                        content=f"[API 错误 HTTP {resp.status_code}] {resp.text[:200]}",
                    )

            except requests.RequestException as e:
                last_error = str(e)[:200]

            # 指数退避
            if attempt < config.model.max_retries - 1:
                time.sleep(2 ** attempt)

        # 全败，返回错误消息而非崩溃
        logger.error(f"API 调用失败（重试 {config.model.max_retries} 次后）: {last_error}")
        return Message(
            role="assistant",
            content=f"[API 调用失败（重试 {config.model.max_retries} 次后）] {last_error}",
        )

    def think_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Generator[tuple[str, object], None, None]:
        """SSE 流式思考：逐 token 产出文本块，实时显示。

        DeepSeek API 的 SSE 格式：
          data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}
          data: {"choices":[{"delta":{"tool_calls":[...]},"index":0}]}
          data: [DONE]

        - tool_calls 的 delta 跨多个 chunk 累积（id/name 在首个，arguments 后续追加）
        - 我们产出 ("text", str) 给 UI 实时显示，"done" 时产出完整 Message
        - 请求阶段支持自动重试（与 think() 一致）
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "temperature": config.model.temperature,
            "max_tokens": config.model.max_tokens,
        }
        if tools:
            payload["tools"] = tools

        last_error = ""
        resp = None
        # timeout 用元组 (connect, read)：read timeout 防止流式过程中
        # 服务器静默不发包导致 iter_lines 无限阻塞
        stream_timeout = (config.model.request_timeout, config.model.request_timeout)
        for attempt in range(config.model.max_retries):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=stream_timeout,
                    stream=True,
                )

                if resp.ok:
                    break  # 成功，进入流式迭代

                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                else:
                    # 4xx 非 429 → 不可重试，直接返回
                    logger.error(f"SSE 不可重试错误 HTTP {resp.status_code}: {resp.text[:200]}")
                    yield ("text", f"[流式请求失败 HTTP {resp.status_code}] {resp.text[:200]}")
                    yield ("done", Message(role="assistant", content=f"[流式请求失败 HTTP {resp.status_code}] {resp.text[:200]}"))
                    return

            except requests.RequestException as e:
                last_error = str(e)[:200]

            if attempt < config.model.max_retries - 1:
                time.sleep(2 ** attempt)

        if resp is None or not resp.ok:
            logger.error(f"SSE 请求失败（重试 {config.model.max_retries} 次后）: {last_error}")
            yield ("text", f"[流式请求失败（重试 {config.model.max_retries} 次后）] {last_error}")
            yield ("done", Message(role="assistant", content=f"[流式请求失败] {last_error}"))
            return

        accumulated: dict[int, dict] = {}  # index → {"id", "function": {"name", "arguments"}}
        full_content = ""

        # 流式迭代阶段：连接中断时若已有累积内容，返回部分结果而非抛异常。
        # 不重试流式迭代——已向用户输出过的文本重发会造成重复显示。
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()  # 去掉 "data:" 前缀，兼容有无空格
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                # 文本块
                content = delta.get("content", "")
                if content:
                    full_content += content
                    yield ("text", content)

                # 工具调用块（需跨 chunk 累积）
                tc_list = delta.get("tool_calls")
                if tc_list:
                    for tc in tc_list:
                        idx = tc.get("index", 0)
                        if idx not in accumulated:
                            # 首个 chunk：携带 id 和 function name
                            accumulated[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": tc.get("function", {}).get("arguments", ""),
                                },
                            }
                        else:
                            # 后续 chunk：追加 arguments
                            args_chunk = tc.get("function", {}).get("arguments", "")
                            if args_chunk:
                                accumulated[idx]["function"]["arguments"] += args_chunk
        except requests.RequestException as e:
            # 流式中断：若已产出内容，标注后返回部分结果；否则报错
            logger.warning(f"流式响应中断: {e}")
            if not full_content and not accumulated:
                yield ("text", f"[流式响应中断] {str(e)[:200]}")
                yield ("done", Message(
                    role="assistant",
                    content=f"[流式响应中断] {str(e)[:200]}",
                ))
                return
            full_content += "\n\n[流式响应中断，以上为已接收的部分内容]"

        # 构建最终 Message
        tool_calls = None
        if accumulated:
            tool_calls = [
                accumulated[i] for i in sorted(accumulated)
            ]

        final_msg = Message(
            role="assistant",
            content=full_content,
            tool_calls=tool_calls,
        )
        yield ("done", final_msg)
