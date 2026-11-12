from __future__ import annotations

import json
from typing import Any

from messages import Message, Opaque, Text, ToolCall, ToolResult
from providers.base import AssistantTurn, StopReason
from usage import from_anthropic

_STOP_REASONS: dict[str | None, StopReason] = {
    "end_turn": "end",
    "stop_sequence": "end",
    "tool_use": "tool_use",
    "max_tokens": "length",
}


def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """把工具定义（项目里的规范格式是 OpenAI schema）转成 Anthropic schema。"""
    return [
        {
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "input_schema": tool["function"]["parameters"],
        }
        for tool in tools
    ]


def to_anthropic_messages(messages: list[Message]) -> list[dict]:
    """IR -> Anthropic messages。system 不在这里，调用 API 时单独传。"""
    wire: list[dict] = []
    for message in messages:
        blocks: list[dict] = []
        if message.role == "user":
            # tool_result 必须排在同一条 user 消息的文本块之前
            blocks.extend(_tool_result_block(r) for r in message.results)
            blocks.extend(
                {"type": "text", "text": part.text}
                for part in message.parts
                if isinstance(part, Text) and part.text
            )
        else:
            for part in message.parts:
                if isinstance(part, Text) and part.text:
                    blocks.append({"type": "text", "text": part.text})
                elif isinstance(part, ToolCall):
                    blocks.append({
                        "type": "tool_use",
                        "id": part.id,
                        "name": part.name,
                        # 截断调用没有合法 JSON，用 {} 占位只为让历史合法
                        "input": part.arguments if part.arguments is not None else {},
                    })
                elif isinstance(part, Opaque) and part.provider == "anthropic":
                    blocks.append(part.payload)
        if blocks:
            wire.append({"role": message.role, "content": blocks})
    return wire


def from_anthropic_message(response: Any) -> AssistantTurn:
    """Anthropic SDK Message -> AssistantTurn。"""
    parts = []
    for block in response.content:
        if block.type == "text":
            parts.append(Text(block.text))
        elif block.type == "tool_use":
            arguments = block.input if isinstance(block.input, dict) else {}
            parts.append(
                ToolCall(
                    id=block.id,
                    name=block.name,
                    raw_arguments=json.dumps(arguments, ensure_ascii=False),
                    arguments=arguments,
                )
            )
            # thinking / redacted_thinking 等，之后请求要原样带回去
        else:
            parts.append(Opaque("anthropic", block.model_dump()))

    return AssistantTurn(
        message=Message("assistant", parts),
        stop_reason=_STOP_REASONS.get(response.stop_reason, "other"),
        usage=from_anthropic(response.usage),
    )


def _tool_result_block(result: ToolResult) -> dict:
    block = {
        "type": "tool_result",
        "tool_use_id": result.tool_call_id,
        "content": result.content,
    }
    if result.is_error:
        block["is_error"] = True
    return block
