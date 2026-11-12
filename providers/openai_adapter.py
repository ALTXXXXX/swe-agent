from __future__ import annotations

from typing import Any

from messages import Message, Opaque, Text, ToolCall
from providers.base import AssistantTurn, StopReason
from usage import from_openai

_STOP_REASONS: dict[str | None, StopReason] = {
    "stop": "end",
    "tool_calls": "tool_use",
    "length": "length",
}


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """工具定义本来就沿用 OpenAI 格式，原样返回（留作接口对齐）。"""
    return tools


def to_openai_messages(system: str, messages: list[Message]) -> list[dict]:
    """IR -> OpenAI messages。system 作为第一条；tool 结果是独立消息。"""
    wire: list[dict] = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "assistant":
            wire.append(_assistant_message(message))
            continue

        # tool 消息必须紧跟在带 tool_calls 的 assistant 之后
        wire.extend(
            {
                "role": "tool",
                "tool_call_id": result.tool_call_id,
                "content": result.content,
            }
            for result in message.results
        )
        text = message.text()
        if text:
            wire.append({"role": "user", "content": text})
    return wire


def _assistant_message(message: Message) -> dict:
    wire: dict = {"role": "assistant", "content": message.text() or None}
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    # 保留原始字符串：参数被截断时也能原样回传
                    "arguments": call.raw_arguments,
                },
            }
            for call in message.tool_calls
        ]
    for part in message.parts:
        if isinstance(part, Opaque) and part.provider == "openai":
            wire.update(part.payload)
    return wire


def from_openai_completion(response: Any) -> AssistantTurn:
    """OpenAI SDK ChatCompletion -> AssistantTurn。"""
    choice = response.choices[0]
    message = choice.message
    parts = []
    if message.content:
        parts.append(Text(message.content))
    # DeepSeek 的 reasoning_content 等非标准字段，之后请求要原样带回去
    extra = getattr(message, "model_extra", None) or {}
    if extra.get("reasoning_content"):
        parts.append(
            Opaque("openai", {"reasoning_content": extra["reasoning_content"]})
        )
    for call in message.tool_calls or []:
        parts.append(
            ToolCall.create(
                id=call.id,
                name=call.function.name,
                raw_arguments=call.function.arguments or "",
            )
        )

    return AssistantTurn(
        message=Message("assistant", parts),
        stop_reason=_STOP_REASONS.get(choice.finish_reason, "other"),
        usage=from_openai(response.usage),
    )
