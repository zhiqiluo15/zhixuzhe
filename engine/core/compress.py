"""上下文压缩 —— 长对话自动摘要，控制发送给模型的输入 token 成本

方案：增量分层摘要
- 保留最近 keep_recent 条完整消息（保证对话连续性，Brain 能直接看到近期上下文）
- 更早的消息按 summarize_chunk 粒度分块，由 Brain 增量压缩为一段「历史对话摘要」
- 摘要随新消息增长而更新（每次合并新块，产出单一完整摘要文本），不重复摘要已压缩部分
- 完整历史仍由 HistoryStore 持久化到会话文件；压缩只影响"发送给模型的上下文"，
  不破坏灵魂层数据，与记忆检索注入（MemoryManager）正交互补

安全设计：
- 摘要调用失败时安全降级为不压缩（返回原始消息列表），不阻断对话主流程
- 摘要文本上限 max_summary_chars 字符，超出截断，防摘要自身撑爆上下文
"""

from typing import Callable

from engine.brain.base import Brain, Message
from engine.log import get_logger

logger = get_logger(__name__)

# 摘要器系统提示词：压缩为简洁中文摘要，保留关键信息
SUMMARIZE_SYSTEM = """你是对话摘要器。将一段对话历史压缩为简洁的中文摘要，保留：
- 用户的需求、偏好、已确认的关键事实
- 已做出的决定、尚未完成的事项
- 重要的背景信息（便于后续对话延续上下文）

规则：
- 只输出纯文本摘要，不要使用任何 markdown 格式或标题
- 用客观语气，不添加原文没有的信息
- 已有摘要时，在原有基础上合并新内容，不要重复已有信息，也不要遗漏"""


class ContextCompressor:
    """增量分层摘要压缩器。

    状态：
    - _summary: 已压缩部分的单一摘要文本
    - _summarized_upto: 已摘要到的 history 索引（含），其前的消息由摘要代表
    """

    def __init__(
        self,
        brain: Brain,
        keep_recent: int = 20,
        summarize_chunk: int = 10,
        max_summary_chars: int = 1500,
        enabled: bool = True,
    ):
        self.brain = brain
        self.keep_recent = max(4, keep_recent)
        self.summarize_chunk = max(2, summarize_chunk)
        self.max_summary_chars = max(200, max_summary_chars)
        self.enabled = enabled
        self._summary = ""
        self._summarized_upto = 0

    # ── 状态管理 ──

    def reset(self) -> None:
        """重置摘要状态（对话 reset 时调用）"""
        self._summary = ""
        self._summarized_upto = 0

    @property
    def summary(self) -> str:
        return self._summary

    # ── 核心入口 ──

    def build(
        self,
        history: list[Message],
        system: Message,
        user_msg: Message,
    ) -> list[Message]:
        """构建发送给模型的上下文消息列表（历史超阈值时自动压缩）。

        返回 [system, (摘要), *保留的完整历史, user]。
        未启用或历史未超阈值时，返回原样 [system] + history + [user]。
        """
        if not self.enabled:
            return [system] + history + [user_msg]

        # reset 后 history 变短：摘要状态必须同步重置，防止索引错位
        if self._summarized_upto > len(history):
            logger.warning(
                f"上下文压缩状态与历史长度不一致"
                f"（已摘要至第 {self._summarized_upto} 条，历史仅 {len(history)} 条），重置压缩状态"
            )
            self.reset()

        cut = len(history) - self.keep_recent
        if cut > self._summarized_upto:
            # 有新增长的可压缩段，分块增量摘要（每次最多处理 2 个块，避免一次性过长）
            pending = history[self._summarized_upto:cut]
            logger.debug(
                f"上下文压缩: 历史 {len(history)} 条，本次可压缩 {len(pending)} 条"
                f"（已摘要至第 {self._summarized_upto} 条，保留最近 {self.keep_recent} 条完整）"
            )
            self._summarize_pending(pending)
        else:
            logger.debug(
                f"上下文压缩: 历史 {len(history)} 条未达压缩阈值"
                f"（已摘要至第 {self._summarized_upto} 条，保留最近 {self.keep_recent} 条完整）"
            )

        if not self._summary:
            return [system] + history + [user_msg]

        ctx_messages = [system]
        ctx_messages.append(Message(
            role="system",
            content="【历史对话摘要】\n" + self._summary,
        ))
        ctx_messages += history[self._summarized_upto:]
        ctx_messages.append(user_msg)
        return ctx_messages

    # ── 内部方法 ──

    def _summarize_pending(self, pending: list[Message]) -> None:
        """将待压缩消息分块增量摘要，更新 _summary 与 _summarized_upto。

        每块大小 = summarize_chunk。单次最多处理 2 块（防恢复超长会话时
        一次性注入过多消息），剩余留待下次 build 时继续。
        """
        max_batch = self.summarize_chunk * 2
        processed = 0
        chunks_done = 0
        while processed < len(pending) and processed < max_batch:
            start = processed
            chunk = pending[start:start + self.summarize_chunk]
            processed = start + len(chunk)
            try:
                new_summary = self._summarize_chunk(chunk)
            except Exception as e:
                logger.warning(
                    f"上下文摘要失败，跳过该块（不阻断主流程）: {e}"
                    f"（块 {start + 1}~{processed} / 本次待压缩 {len(pending)} 条）"
                )
                break
            if new_summary:
                self._summary = new_summary[:self.max_summary_chars]
                logger.debug(
                    f"上下文摘要块 {start + 1}~{processed} 成功，合并后摘要 {len(self._summary)} 字符"
                )
            else:
                logger.debug(
                    f"上下文摘要块 {start + 1}~{processed} 返回空文本，仅推进指针（内容可能全为空消息）"
                )
            self._summarized_upto += len(chunk)
            chunks_done += 1
        logger.info(
            f"上下文压缩推进: 处理 {chunks_done} 块（本次 {len(pending)} 条中的 {processed} 条），"
            f"已摘要至历史第 {self._summarized_upto} 条，摘要共 {len(self._summary)} 字符"
        )

    def _summarize_chunk(self, chunk: list[Message]) -> str:
        """调用 Brain 合并摘要：已有摘要 + 新块 → 更新后的完整摘要"""
        lines = []
        for m in chunk:
            role_label = {
                "user": "用户",
                "assistant": "助手",
                "tool": "工具结果",
                "system": "系统",
            }.get(m.role, m.role)
            content = m.content if m.content else ""
            # 工具调用消息内容可能为空，附工具名辅助摘要
            if m.tool_calls:
                names = ", ".join(
                    tc.get("function", {}).get("name", "")
                    for tc in m.tool_calls if tc.get("function")
                )
                if names:
                    content = (content + f" [调用工具: {names}]").strip()
            if content:
                lines.append(f"[{role_label}] {content}")

        conversation = "\n".join(lines)
        if not conversation:
            return ""

        summary_text = self._summary or "（无）"
        user_prompt = (
            f"已有摘要：\n{summary_text}\n\n"
            f"以下是需要合并进摘要的新对话：\n{conversation}"
        )
        messages = [
            Message(role="system", content=SUMMARIZE_SYSTEM),
            Message(role="user", content=user_prompt),
        ]
        response = self.brain.think(messages)
        return (response.content or "").strip()
