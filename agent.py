

from pathlib import Path
from permissions import chek_permission
import sys
from context import (
    tool_result_budget,
    micro_compact,
    estimate_tokens,
    compact_keep_index,
    render_transcript,
    write_transcript,
    SUMMARY_SYSTEM_PROMPT,
    COMPACT_TRIGGER_TOKENS,
    COMPACT_KEEP_RECENT_TURNS,
    MAX_COMPACT_FAILURES,
)
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from dotenv import load_dotenv
from session import save_session
from tools import tool_definitions, execute_tool, CONCURRENCY_SAFE_TOOLS
import uuid
import time
from typing import Callable, Awaitable
import os
from prompt import (
    build_static_system_prompt,
    build_dynamic_system_prompt,
    build_user_context_reminder,
)
from pricing import resolve, cost_of
from usage import TokenUsage
from datetime import datetime
from zoneinfo import ZoneInfo
from rich.console import Console
from rich.text import Text as RichText
import asyncio
from ui import print_tool_call, print_tool_result, print_text_delta
from messages import (
    Message,
    ToolCall,
    ToolResult,
    fill_missing_tool_results,
    interrupted_tool_results,
    message_from_dict,
    message_to_dict,
)
from providers import create_provider

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
load_dotenv()

console = Console()


MODEL_PRICES = {

}


class Agent:

    def __init__(
    self,
    *,
    provider: str = "openai",
    permission_mode: str = "default",
    model: str = "deepseek-flash",
    api_base: str | None = None,
    api_key: str | None = None,
    thinking: bool = False,
    stream: bool = True,             # 是否流式输出
    max_tokens: int = 4096,          # Anthropic 必填参数，OpenAI 忽略
    max_cost_usd: float | None = None,
    max_turns: int | None = None,
    confirm_fn: Callable[[str], Awaitable[bool]] | None = None,
    custom_system_prompt: str | None = None,
    custom_tools: list[dict] | None = None,
    is_sub_agent: bool = False):
        #参数全量入库
        self.provider = provider
        self.permission_mode = permission_mode
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.thinking = thinking
        self.stream = stream
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.max_turns = max_turns
        self.confirm_fn = confirm_fn
        self.is_sub_agent = is_sub_agent

        self.system_prompt = custom_system_prompt or (
            build_static_system_prompt() + build_dynamic_system_prompt()
        )

        self.tools = custom_tools if custom_tools is not None else tool_definitions

        if provider == "openai":
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=api_base or "https://api.deepseek.com",
            )
        elif provider == "anthropic":
            client = AsyncAnthropic(api_key=api_key, base_url=api_base)
        else:
            raise ValueError(f"未知 provider: {provider}")

        self.provider_impl = create_provider(
            provider, client=client, model=model, max_tokens=max_tokens
        )
        # 工具 schema 只转换一次，之后每次请求复用
        self.tool_schema = self.provider_impl.tool_schema(self.tools)

        self.session_id = uuid.uuid4().hex[:8]
        self.session_start_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        #运行时计数器（max_turns / max_cost_usd 靠它俩）
        self.turn_count = 0
        #累计统计费用
        self.total_cost_usd = 0.0
        #计价规则
        self.pricing = resolve(self.model, self.api_base)
        #统计费用
        self.usage = TokenUsage()
        self.turn_usage = TokenUsage()  # 当前轮对话累计
        self.total_api_calls = 0
        self.turn_cost_usd = 0.0
        self.uncached_input_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.output_tokens = 0
        self.compact_failures = 0   # 连续压缩失败次数（熔断）

        # 唯一的会话历史：规范化消息 IR
        self.messages: list[Message] = []

    def show_usage(self):
        turn_input = self.turn_usage.prompt_tokens
        turn_output = self.turn_usage.output
        turn_total = turn_input + turn_output

        total_tokens = self.usage.prompt_tokens + self.usage.output

        line = RichText()

        line.append("◈ Usage ", style="bold cyan")
        line.append("│ ", style="dim")

        line.append("Turn ", style="dim")
        line.append(f"{turn_total:,}", style="bold white")

        line.append(" (", style="dim")
        line.append(f"↑{turn_input:,}", style="green")
        line.append(" ", style="dim")
        line.append(f"↓{turn_output:,}", style="blue")
        line.append(")", style="dim")

        line.append(" │ ", style="dim")

        line.append("Total ", style="dim")
        line.append(f"{total_tokens:,}", style="bold white")

        line.append(" │ ", style="dim")

        line.append("Cost ", style="dim")
        line.append(f"${self.total_cost_usd:.6f}", style="bold green")

        console.print(line)

    def _get_message_count(self) -> int:
        return len(self.messages)

    def _show_cost(self) -> None:
        print(f"累计 API 调用：{self.total_api_calls}次")
        print(f"累计花费：${self.total_cost_usd:.4f}")

    def auto_save(self) -> None:
        # 会话只存规范化 IR，与 provider 无关
        data = {
            "metadata": {
                "id": self.session_id,
                "provider": self.provider,
                "model": self.model,
                "cwd": str(Path.cwd()),
                "startTime": self.session_start_time,
                "messageCount": self._get_message_count(),
                "format": "ir-v1",
            },
            "messages": [message_to_dict(m) for m in self.messages],
        }
        save_session(self.session_id, data)

    def restore_session(self, data: dict) -> None:
        raw = data.get("messages")
        if raw is None:
            print("旧版会话格式不受支持，跳过恢复")
            return
        self.messages = [message_from_dict(item) for item in raw]

    def replay_history(self) -> None:
        """恢复会话后回放历史消息（没有文本的消息自动跳过）。"""
        for message in self.messages:
            content = message.text()
            if not content:
                continue
            if message.role == "user":
                print(f"User: {content}")
            else:
                print(f"AI: {content}")

    def clear_history(self) -> None:
        self.messages = []
        print("已清空对话历史")

    def _record_usage(self, usage: TokenUsage) -> None:
        """记录一次调用的 token 与费用（usage 已由适配器归一化）。"""
        rates = self.pricing.rates_at(datetime.now(BEIJING_TZ))
        cost = cost_of(usage, rates)
        self.usage += usage
        self.turn_usage += usage
        self.total_cost_usd += cost
        self.turn_cost_usd += cost

    def _check_permission(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """按当前权限模式决定是否执行工具，返回 (是否允许, 拒绝原因)。

        confirm 状态下在终端询问用户；拒绝原因会作为工具结果回传给模型，
        这样模型能知道调用被拦下，而不是以为工具执行成功了。
        """
        if not isinstance(arguments, dict):
            return False, f"工具参数错误：期望对象，收到 {type(arguments).__name__}"

        decision = chek_permission(tool_name, arguments, self.permission_mode)
        action = decision.get("action", "deny")
        message = decision.get("message") or tool_name
 
        if action == "allow":
            return True, ""
        if action == "deny":
            return False, f"权限拒绝：{message}"

        # action == "confirm"：当前是同步 REPL，直接用 input() 询问
        answer = input(f"\n需要确认：{message}\n允许执行？[y/N] ")
        if answer.strip().lower() in ("y", "yes"):
            return True, ""
        return False, f"用户拒绝执 行：{message}"

    def _begin_turn(self, user_message: str) -> int:
        """追加用户消息并重置本轮计数，返回可回滚的历史长度。"""
        history_len = len(self.messages)
        if history_len == 0:
            # reminder 拼接到第一条用户消息前面
            remind = build_user_context_reminder()
            user_message = f"{remind}\n\n{user_message}"
        self.messages.append(Message.user(user_message))
        self.turn_count = 0
        self.turn_usage = TokenUsage()
        self.turn_cost_usd = 0.0
        return history_len

    async def _summarize(self, messages: list[Message]) -> str:
        """把旧历史压成摘要（1 次 API 调用）。"""
        turn = await self.provider_impl.generate(
            system=SUMMARY_SYSTEM_PROMPT,
            messages=[Message.user(render_transcript(messages))],
            tools=self.tool_schema,
            stream=False,
        )
        summary = turn.message.text().strip()
        if not summary:
            raise RuntimeError("摘要结果为空")
        return summary

    async def _maybe_compact(self) -> None:
        """接近窗口阈值时：落盘 transcript → LLM 摘要 → 摘要 + 最近 N 轮。"""
        if estimate_tokens(self.messages) < COMPACT_TRIGGER_TOKENS:
            return
        if self.compact_failures >= MAX_COMPACT_FAILURES:
            return
        keep_from = compact_keep_index(self.messages, COMPACT_KEEP_RECENT_TURNS)
        if keep_from is None:
            return
        try:
            path = write_transcript(self.session_id, self.messages)
            summary = await self._summarize(self.messages[:keep_from])
            self.messages[:] = (
                [Message.user(f"[Compacted]\n\n{summary}")]
                + self.messages[keep_from:]
            )
            self.compact_failures = 0
            console.print(f"[dim]◈ Context compacted · transcript: {path}[/dim]")
        except Exception as e:
            self.compact_failures += 1
            print(
                f"警告：上下文压缩失败"
                f"（{self.compact_failures}/{MAX_COMPACT_FAILURES}）：{e}"
            )

    async def chat_once(self, user_message: str) -> None:
        # 每次对话开始前修复缺结果的工具调用：两家 API 都要求历史合法
        fill_missing_tool_results(self.messages)

        # 上下文接近窗口上限时，先把历史压成摘要再开始新一轮
        await self._maybe_compact()

        history_len = self._begin_turn(user_message)

        while True:
            if self.max_turns is not None and self.turn_count >= self.max_turns:
                print(f"已达到最大轮数（{self.max_turns}），强制停止。")
                return
            self.turn_count += 1

            # 流式期间提前启动的并发安全工具（按 tool_call id）
            early_tasks: dict[str, asyncio.Task] = {}
            # 流式阶段已判定不能执行的结果（按 tool_call id）
            early_results: dict[str, str] = {}

            async def on_tool_call_complete(call: ToolCall) -> None:
                """某个工具参数收齐：并发安全的只读工具可以提前执行。"""
                if call.name not in CONCURRENCY_SAFE_TOOLS:
                    return
                arguments = call.arguments or {}
                # 并发安全工具全是读操作，权限判断是纯规则匹配，
                # 不会走到 input()，同步调用不会阻塞事件循环
                allowed, reason = self._check_permission(call.name, arguments)
                if not allowed:
                    early_results[call.id] = f"Error: {reason}"
                    return
                print_tool_call(call.name, arguments)
                early_tasks[call.id] = asyncio.create_task(
                    execute_tool(call.name, arguments)

                )
            #大结果落盘
            tool_result_budget(self.messages)
            micro_compact(self.messages)
            try:
                try:
                    turn = await self.provider_impl.generate(
                        system=self.system_prompt,
                        messages=self.messages,
                        tools=self.tool_schema,
                        stream=self.stream,
                        on_text=print_text_delta,
                        on_tool_call_complete=on_tool_call_complete,
                    )
                except KeyboardInterrupt:
                    console.print()
                    print("已中断本轮对话")
                    del self.messages[history_len:]
                    return
                except Exception as e:
                    console.print()
                    print(f"调用失败：{e}")
                    del self.messages[history_len:]
                    return

                self.total_api_calls += 1
                self._record_usage(turn.usage)
                self.messages.append(turn.message)

                text = turn.message.text()
                if text:
                    if self.stream:
                        # 流式文本可能没有以换行结尾，接工具输出/usage 前补一个换行
                        console.print()
                    else:
                        print("AI: ", text)

                if turn.tool_calls:
                    if turn.stop_reason == "tool_use":
                        result_message = await self._execute_tools(
                            turn.tool_calls, early_tasks, early_results
                        )
                    else:
                        # 生成被截断时参数可能不完整：不执行，但必须补结果，
                        # 否则历史非法，下一次请求会被拒绝
                        result_message = interrupted_tool_results(
                            turn.tool_calls, turn.stop_reason
                        )
                        for call, result in zip(
                            turn.tool_calls, result_message.results
                        ):
                            print_tool_result(call.name, result.content)
                        if turn.stop_reason == "length":
                            print("输出达到长度上限，工具调用未执行，请重试。")
                    self.messages.append(result_message)
                    continue

                if turn.stop_reason == "length":
                    print("输出达到长度上限，回答可能不完整。")
                elif turn.stop_reason != "end":
                    print(f"模型停止生成，原因：{turn.stop_reason}")

                self.show_usage()
                return
            finally:
                # 异常/中断/未被取走的提前任务统一取消
                for task in early_tasks.values():
                    task.cancel()
                if early_tasks:
                    await asyncio.gather(
                        *early_tasks.values(), return_exceptions=True
                    )

    async def _execute_tools(
        self,
        calls: list[ToolCall],
        early_tasks: dict[str, asyncio.Task],
        early_results: dict[str, str],
    ) -> Message:
        """执行本轮全部工具调用，返回一条 user 侧的工具结果消息。

        流式阶段已提前启动或被权限拒绝的调用按 id 取回，不会重复执行。
        """
        results: list[ToolResult] = []
        for call in calls:
            arguments = call.arguments
            is_error = False

            if call.id in early_results:
                # 流式阶段已判定（比如被权限拒绝）
                result = early_results.pop(call.id)
                is_error = True
            elif call.id in early_tasks:
                # 流式阶段已启动，等它跑完
                task = early_tasks.pop(call.id)
                try:
                    result = await task
                except Exception as e:
                    result = f"Error: 工具执行失败：{e}"
                    is_error = True
            elif arguments is None:
                result = "Error: 工具参数 JSON 解析失败，请修正后重试"
                is_error = True
            else:
                try:
                    allowed, reason = self._check_permission(call.name, arguments)
                    if allowed:
                        print_tool_call(call.name, arguments)
                        result = await execute_tool(call.name, arguments)
                    else:
                        result = f"Error: {reason}"
                        is_error = True
                except Exception as e:
                    result = f"Error: 工具执行失败：{e}"
                    is_error = True

            text = str(result)
            print_tool_result(call.name, text)
            results.append(ToolResult(call.id, text, is_error=is_error))

        return Message.tool_results(results)

    async def run(self):
        while True:
            user_message = input("User: ")

            if user_message.strip().lower() in ("exit", ""):
                print("Bye!")
                break
            await self.chat_once(user_message)
            self.auto_save()


if __name__ == "__main__":
    # 密钥只从环境变量读取，禁止再写死到代码里
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("未找到 ANTHROPIC_API_KEY / OPENAI_API_KEY，请在 .env 中配置")
    agent = Agent(
        provider="anthropic",
        api_base="https://api.deepseek.com/anthropic",
        api_key=api_key,
    )
    asyncio.run(agent.chat_once("你好，请介绍一下自己"))
