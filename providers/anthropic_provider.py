from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from messages import Message, ToolCall
from providers.anthropic_adapter import (
    from_anthropic_message,
    to_anthropic_messages,
    to_anthropic_tools,
)
from providers.base import AssistantTurn


class AnthropicProvider:
    """Anthropic 后端的 Provider 实现：只做序列化 + SDK 调用。"""

    name = "anthropic"

    def __init__(self, *, client: Any, model: str, max_tokens: int = 4096):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def tool_schema(self, tools: list[dict]) -> list[dict]:
        return to_anthropic_tools(tools)

    async def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict],
        stream: bool,
        on_text: Callable[[str], None] | None = None,
        on_tool_call_complete: Callable[[ToolCall], Awaitable[None]] | None = None,
    ) -> AssistantTurn:
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": to_anthropic_messages(messages),
            "tools": tools,
        }
        if not stream:
            # AsyncAnthropic 必须 await，同步调用会阻塞事件循环
            response = await self.client.messages.create(**kwargs)
            return from_anthropic_message(response)
        tool_blocks: dict[int, dict] = {}

        async with self.client.messages.stream(**kwargs) as stream_obj:
            async for event in stream_obj:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tool_blocks[event.index] = {
                            "id": block.id,
                            "name": block.name,
                            "input_json": "",
                        }
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        if on_text is not None:
                            on_text(delta.text)
                    elif delta.type == "input_json_delta":
                        tracked = tool_blocks.get(event.index)
                        if tracked is not None:
                            tracked["input_json"] += delta.partial_json
                elif event.type == "content_block_stop" and on_tool_call_complete:
                    tracked = tool_blocks.pop(event.index, None)
                    if tracked is None:
                        continue
                    try:
                        # 没有参数的工具有时不给 partial_json，按 {} 处理
                        arguments = json.loads(tracked["input_json"] or "{}")
                    except json.JSONDecodeError:
                        # 参数没收完整：不提前执行，交给最终消息兜底
                        continue
                    if not isinstance(arguments, dict):
                        continue
                    await on_tool_call_complete(
                        ToolCall(
                            id=tracked["id"],
                            name=tracked["name"],
                            raw_arguments=tracked["input_json"] or "{}",
                            arguments=arguments,
                        )
                    )
            final_message = await stream_obj.get_final_message()

        return from_anthropic_message(final_message)
