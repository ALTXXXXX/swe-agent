from __future__ import annotations

from typing import Any, Awaitable, Callable

from openai import LengthFinishReasonError

from messages import Message, ToolCall
from providers.base import AssistantTurn
from providers.openai_adapter import (
    from_openai_completion,
    to_openai_messages,
    to_openai_tools,
)


class OpenAIProvider:
    """OpenAI 兼容后端的 Provider 实现：只做序列化 + SDK 调用。"""

    name = "openai"

    def __init__(self, *, client: Any, model: str):
        self.client = client
        self.model = model

    def tool_schema(self, tools: list[dict]) -> list[dict]:
        return to_openai_tools(tools)

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
        wire = to_openai_messages(system, messages)
        if not stream:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=wire,
                tools=tools,
                stream=False,
            )
            return from_openai_completion(response)

        try:
            async with self.client.chat.completions.stream(
                model=self.model,
                messages=wire,
                tools=tools,
                stream_options={"include_usage": True},
            ) as stream_obj:
                async for event in stream_obj:
                    if event.type == "content.delta" and on_text is not None:
                        on_text(event.delta)
                completion = await stream_obj.get_final_completion()
        except LengthFinishReasonError as e:
            # 输出达到长度上限时 SDK 不返回正常 completion，
            # 真实 usage 和已生成内容都在异常对象里，不能丢
            completion = e.completion

        # OpenAI 流式暂不支持 tool_call 提前执行，工具在流结束后统一执行；
        # on_tool_call_complete 保留是为了和 Anthropic 接口对齐。
        return from_openai_completion(completion)
