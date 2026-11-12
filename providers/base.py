from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Protocol

from messages import Message, ToolCall
from usage import TokenUsage

StopReason = Literal["end", "tool_use", "length", "other"]


@dataclass(slots=True)
class AssistantTurn:
    """一次模型调用的归一化结果，主循环只认这个结构。"""

    message: Message            # 已归一化的 assistant 消息，可直接追加进历史
    stop_reason: StopReason
    usage: TokenUsage

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls


class Provider(Protocol):
    """只负责 wire 格式转换和 SDK 调用，不含任何策略。"""

    name: str

    def tool_schema(self, tools: list[dict]) -> Any: ...

    async def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: Any,
        stream: bool,
        on_text: Callable[[str], None] | None = None,
        on_tool_call_complete: Callable[[ToolCall], Awaitable[None]] | None = None,
    ) -> AssistantTurn: ...
