"""provider 适配层：只负责 wire 格式转换和 SDK 调用，不含任何策略。"""

from typing import Any

from providers.anthropic_provider import AnthropicProvider
from providers.base import AssistantTurn, Provider, StopReason
from providers.openai_provider import OpenAIProvider

__all__ = [
    "AnthropicProvider",
    "AssistantTurn",
    "OpenAIProvider",
    "Provider",
    "StopReason",
    "create_provider",
]


def create_provider(
    name: str,
    *,
    client: Any,
    model: str,
    max_tokens: int = 4096,
) -> Provider:
    """按 provider 名字实例化适配器；client 由调用方注入，便于测试。"""
    if name == "anthropic":
        return AnthropicProvider(client=client, model=model, max_tokens=max_tokens)
    if name == "openai":
        return OpenAIProvider(client=client, model=model)
    raise ValueError(f"未知 provider: {name}")
