"""规范化的消息中间表示（IR）。

会话历史只保存这一种结构；OpenAI / Anthropic 各自的 wire 格式由
providers/*_adapter.py 在请求边界转换，主循环、权限、上下文管理
都只操作这里定义的类型。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass(slots=True)
class Text:
    text: str


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    raw_arguments: str              # 原始 JSON 字符串：截断时也要能原样回传
    arguments: dict | None = None   # 解析成功才填；截断/非法 JSON 为 None

    @classmethod
    def create(cls, *, id: str, name: str, raw_arguments: str) -> "ToolCall":
        try:
            value = json.loads(raw_arguments) if raw_arguments.strip() else {}
            parsed = value if isinstance(value, dict) else None
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return cls(id=id, name=name, raw_arguments=raw_arguments, arguments=parsed)


@dataclass(slots=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(slots=True)
class Opaque:
    """provider 私有但必须原样回传的内容：thinking / reasoning_content 等。"""

    provider: str
    payload: dict


Part = Text | ToolCall | ToolResult | Opaque


@dataclass(slots=True)
class Message:
    role: Role
    parts: list[Part] = field(default_factory=list)

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls("user", [Text(text)])

    @classmethod
    def tool_results(cls, results: list[ToolResult]) -> "Message":
        return cls("user", list(results))

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [p for p in self.parts if isinstance(p, ToolCall)]

    @property
    def results(self) -> list[ToolResult]:
        return [p for p in self.parts if isinstance(p, ToolResult)]

    def text(self) -> str:
        return "\n".join(
            p.text for p in self.parts if isinstance(p, Text)
        ).strip()


_INTERRUPTED = (
    "Error: 工具调用未完成（stop_reason={reason}），"
    "参数可能不完整，未执行。请重新发起该工具调用。"
)


def _interrupted_results(calls: list[ToolCall], reason: str) -> list[ToolResult]:
    return [
        ToolResult(call.id, _INTERRUPTED.format(reason=reason), is_error=True)
        for call in calls
    ]


def interrupted_tool_results(calls: list[ToolCall], reason: str) -> Message:
    """输出被截断时为未执行的工具调用补结果，保证历史合法。"""
    return Message.tool_results(_interrupted_results(calls, reason))


def fill_missing_tool_results(messages: list[Message]) -> None:
    """补齐历史里没有对应结果的 tool_call（原地修改）。

    历史里一旦出现 tool_call，紧接着的 user 消息就必须包含它的结果，
    否则下一次请求会被服务端拒绝；两家 API 都是这个约束。
    """
    index = 0
    while index < len(messages):
        message = messages[index]
        calls = message.tool_calls if message.role == "assistant" else []
        if not calls:
            index += 1
            continue

        following = messages[index + 1] if index + 1 < len(messages) else None
        answered = (
            {result.tool_call_id for result in following.results}
            if following is not None and following.role == "user"
            else set()
        )
        missing = [call for call in calls if call.id not in answered]
        if not missing:
            index += 2
            continue

        results = _interrupted_results(missing, "interrupted")
        if following is not None and following.role == "user":
            # tool_result 必须排在紧随其后的 user 消息最前面
            following.parts[:0] = results
        else:
            messages.insert(index + 1, Message.tool_results(results))
        index += 2


# ---------------- 会话序列化 ----------------

def message_to_dict(message: Message) -> dict:
    """IR -> 可 JSON 序列化的 dict（会话存储用）。"""
    return {
        "role": message.role,
        "parts": [_part_to_dict(part) for part in message.parts],
    }


def _part_to_dict(part: Part) -> dict:
    if isinstance(part, Text):
        return {"type": "text", "text": part.text}
    if isinstance(part, ToolCall):
        return {
            "type": "tool_call",
            "id": part.id,
            "name": part.name,
            "raw_arguments": part.raw_arguments,
        }
    if isinstance(part, ToolResult):
        return {
            "type": "tool_result",
            "tool_call_id": part.tool_call_id,
            "content": part.content,
            "is_error": part.is_error,
        }
    if isinstance(part, Opaque):
        return {"type": "opaque", "provider": part.provider, "payload": part.payload}
    raise TypeError(f"未知消息块类型：{type(part).__name__}")


def message_from_dict(data: dict) -> Message:
    """会话存储的 dict -> IR；ToolCall 的参数会重新解析。"""
    return Message(
        role=data["role"],
        parts=[_part_from_dict(item) for item in data.get("parts", [])],
    )


def _part_from_dict(data: dict) -> Part:
    kind = data.get("type")
    if kind == "text":
        return Text(data.get("text", ""))
    if kind == "tool_call":
        return ToolCall.create(
            id=data["id"],
            name=data["name"],
            raw_arguments=data.get("raw_arguments", ""),
        )
    if kind == "tool_result":
        return ToolResult(
            data["tool_call_id"],
            data.get("content", ""),
            bool(data.get("is_error", False)),
        )
    if kind == "opaque":
        return Opaque(data["provider"], data.get("payload", {}))
    raise ValueError(f"未知消息块类型：{kind}")
