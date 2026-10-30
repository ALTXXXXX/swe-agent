from dataclasses import dataclass


@dataclass(slots=True)
class TokenUsage:
    uncached_input: int = 0
    cache_read: int = 0
    cache_write: int = 0  # 写缓存（DeepSeek 恒 0）
    output: int = 0


    def __iadd__(self, o: "TokenUsage"):
        self.uncached_input += o.uncached_input
        self.cache_read += o.cache_read
        self.cache_write += o.cache_write
        self.output += o.output
        return self

    
    @property
    def prompt_tokens(self) -> int:
        return self.uncached_input + self.cache_read + self.cache_write



# provider适配器

def from_openai(u) -> TokenUsage:
    if u is None: return TokenUsage()
    prompt = getattr(u,"prompt_tokens",0) or 0
    cached = min(max(_cached_tokens(u),0), prompt)

    return TokenUsage(
        uncached_input= prompt - cached,
        cache_read= cached,
        cache_write = 0, # OpenAI/DeepSeek 没有独立写费用
        output=getattr(u,"completion_tokens",0) or 0
    )





def _cached_tokens(u) -> int:
    details = getattr(u, "prompt_tokens_details", None)
    v = getattr(details, "cached_tokens", None) if details is not None else None
    if v:
        return int(v)
    extra = getattr(u, "model_extra", None) or {}   # DeepSeek 顶层字段
    return int(extra.get("prompt_cache_hit_tokens")
               or extra.get("cached_tokens") or 0)


def format_usage(usage: TokenUsage) -> str:
    total = usage.prompt_tokens + usage.output

    return (
        f"本轮 {total:,} "
        f"(↑{usage.prompt_tokens:,} ↓{usage.output:,})"
    )