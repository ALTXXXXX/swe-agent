from datetime import datetime, time
from zoneinfo import ZoneInfo
from usage import TokenUsage
from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable
from zoneinfo import ZoneInfo
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _beijing_peak(now: datetime) -> bool:
    # 统一转换为北京时间
    now = now.astimezone(BEIJING_TZ)

    # 获取星期：周一 = 0，周日 = 6
    weekday = now.weekday()

    # 周六、周日不是工作日
    if weekday >= 5:
        return False

    # 获取当前时分
    current_time = now.time()

    # 上午 9:00～12:00，下午 14:00～18:00
    morning = time(9, 0) <= current_time < time(12, 0)
    afternoon = time(14, 0) <= current_time < time(18, 0)

    return morning or afternoon



@dataclass(frozen=True)
class Rates:                       # USD / 1M tokens
    input: float
    cache_read: float
    output: float
    cache_write: float | None = None   # None → 按 input 价收（DeepSeek）


@dataclass(frozen=True)
class Profile:
    off_peak: Rates
    peak: Rates | None = None
    is_peak: Callable[[datetime], bool] | None = None

    def rates_at(self, now: datetime) -> Rates:
        if self.peak is not None and self.is_peak is not None:
            if self.is_peak(now):
                return self.peak

        return self.off_peak


PROFILES = {
    "deepseek": Profile(
        off_peak=Rates(
            input=0.15,
            cache_read=0.003,
            output=0.60,
        ),
        peak=Rates(
            input=0.30,
            cache_read=0.006,
            output=1.20,
        ),
        is_peak=_beijing_peak,
    ),

    "default": Profile(
        off_peak=Rates(
            input=3.0,
            cache_read=0.3,
            output=15.0,
            cache_write=3.75,
        )
    ),
}



def resolve(model: str, api_base: str | None) -> Profile:
    m = (model or "").lower()

    if m.startswith("deepseek"):
        return PROFILES["deepseek"]

    if api_base and "deepseek" in api_base.lower():
        return PROFILES["deepseek"]

    print(f"no pricing profile for {model}; using default")
    return PROFILES["default"]

def cost_of(usage: TokenUsage, rates: Rates) -> float:
    write = rates.cache_write if rates.cache_write is not None else rates.input
    return (
        usage.uncached_input * rates.input
        + usage.cache_read * rates.cache_read
        + usage.cache_write * write
        + usage.output * rates.output
    ) / 1_000_000