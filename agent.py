

from pathlib import Path
import sys
import anthropic
from anthropic.resources import messages
from openai import OpenAI, chat
from dotenv import load_dotenv
from openai.types.responses import tool
from session import save_session
from tools import tool_definitions,execute_tool
import uuid
import time
from typing import Callable, Awaitable
import os
import json
from prompt import build_static_system_prompt,build_dynamic_system_prompt,build_user_context_reminder
from pricing import resolve, cost_of
import tools
from usage import TokenUsage, from_openai,from_anthropic
from datetime import datetime
from zoneinfo import ZoneInfo
from rich.console import Console
from anthropic import Anthropic
from rich.text import Text
from ui import print_tool_call, print_tool_result
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
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.max_turns = max_turns
        self.confirm_fn = confirm_fn
        self.is_sub_agent = is_sub_agent    

        self.system_prompt = custom_system_prompt or (
            build_static_system_prompt() + build_dynamic_system_prompt()
        )

        self.tools = custom_tools if custom_tools is not None else tool_definitions
        # Anthropic 使用独立 schema，待 adapters.to_anthropic_tools 实现后填充
        self.anthropic_tools = self.convert_to_anthropic_tools()

        if self.provider == "openai":
            self.openai_client = OpenAI(
                api_key=api_key,
                base_url = api_base or "https://api.deepseek.com"
            )
            self.anthropic_client = None
        elif self.provider == "anthropic":
            self.anthropic_client = Anthropic(
                api_key=api_key,
                base_url = api_base
            )
            self.openai_client = None
        else:
            raise ValueError(f"未知 provider: {provider}")
        
       
        self.session_id = uuid.uuid4().hex[:8]
        self.session_start_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        #运行时计数器（max_turns / max_cost_usd 靠它俩）
        self.turn_count = 0
        #累计统计费用
        self.total_cost_usd = 0.0
        #计价规则
        self.pricing =resolve(self.model,self.api_base)
        #统计费用
        self.usage = TokenUsage()
        self.turn_usage = TokenUsage()  # 当前轮对话累计
        self.total_api_calls = 0
        self.turn_cost_usd = 0.0
        self.uncached_input_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.output_tokens = 0

        #双后端
         #设置messages
        self.openai_messages = [
            {
                "role": "system",
                "content": self.system_prompt
            }
        ]
        self.anthropic_messages = []

    @property
    def _active_messages(self) -> list[dict]:
        """当前 provider 对应的消息列表。"""
        if self.provider == "anthropic":
            return self.anthropic_messages
        return self.openai_messages


    # #执行天气查询的工具
    # def get_weather(self,location):
    #     return f"当前{location}的天气是晴朗，25摄氏度"


    def show_usage(self):
        turn_input = self.turn_usage.prompt_tokens
        turn_output = self.turn_usage.output
        turn_total = turn_input + turn_output

        total_tokens = self.usage.prompt_tokens + self.usage.output

        line = Text()

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
        return len(self._active_messages)

    def _show_cost(self) -> None:
        print(f"累计 API 调用：{self.total_api_calls}次")
        print(f"累计花费：${self.total_cost_usd:.4f}")


    def auto_save(self) -> None:
        # chat的时候，把当前 provider 的 messages 存放到 json 文件中
        data = {
            "metadata": {
                "id": self.session_id,
                "provider": self.provider,
                "model": self.model,
                "cwd": str(Path.cwd()),
                "startTime": self.session_start_time,
                "messageCount": self._get_message_count(),
            },
        }
        if self.provider == "anthropic":
            data["anthropicMessages"] = self.anthropic_messages or None
        else:
            data["openaiMessages"] = self.openai_messages or None
        save_session(self.session_id, data)


    def restore_session(self,data: dict)-> None:
        # 旧会话没有 provider 字段，按 openai 处理
        session_provider = data.get("metadata", {}).get("provider", "openai")
        if session_provider != self.provider:
            print(f"会话 provider 为 {session_provider}，与当前 {self.provider} 不一致，跳过恢复")
            return

        if self.provider == "anthropic":
            self.anthropic_messages = data.get("anthropicMessages") or []
        else:
            self.openai_messages = data.get("openaiMessages") or self.openai_messages







    def _message_text(self, msg: dict) -> str:
        """提取消息中的纯文本（兼容 OpenAI 字符串与 Anthropic block 列表）。"""
        content = msg.get("content") or ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "\n".join(part for part in parts if part).strip()
        return ""

    def replay_history(self) -> None:
        """恢复会话后回放历史消息（跳过 system 和 tool 消息）"""
        for msg in self._active_messages:
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            content = self._message_text(msg)
            if not content:
                continue
            if role == "user":
                print(f"User: {content}")
            else:
                print(f"AI: {content}")

    def clear_history(self) -> None:
        # OpenAI 保留 system 消息；Anthropic 的 system 不在消息列表里，直接清空
        if self.provider == "anthropic":
            self.anthropic_messages = []
        else:
            self.openai_messages = [self.openai_messages[0]]
        print("已清空对话历史")




    def _record_usage(self,usage):
        #计算token消耗
        if self.provider == "anthropic":
            delta = from_anthropic(usage)
        else:
            delta =  from_openai(usage)

        #根据当前时间选择价格
        now = datetime.now(BEIJING_TZ)
        rates = self.pricing.rates_at(now)
        #计算费用
        cost =cost_of(delta,rates)
        #累加token和费用
        self.usage += delta
        self.turn_usage += delta
        self.total_cost_usd += cost
        self.turn_cost_usd += cost
        return delta,cost




    # def show_usage(self, turn_usage: TokenUsage):
    #     turn_total = turn_usage.prompt_tokens + turn_usage.output
    #     total = self.usage.prompt_tokens + self.usage.output

    #     print(
    #         f"\n[Tokens] "
    #         f"本轮 {turn_total:,} "
    #         f"(↑{turn_usage.prompt_tokens:,} ↓{turn_usage.output:,})"
    #         f" | 累计 {total:,}"
    #         f" | Cost ${self.total_cost_usd:.6f}"
    #     )

    #处理一轮用户对话

    def chat_once(self,user_message):
        if self.provider == "openai":
            self._chat_openai(user_message)
        elif self.provider == "anthropic":
            print("anthropic调用")
            self._chat_anthropic(user_message)

    def convert_to_anthropic_tools(self):
        """讲openai格式的工具定义转换为Anthropic的格式"""
        anthropic_tools = []

        for tool in self.tools:
            function = tool["function"]
            anthropic_tools.append({
                "name":function["name"],
                "description":function["description"],
                "input_schema":function["parameters"]
            })
        return anthropic_tools




    def _chat_anthropic(self,user_message):
        history_len = len(self.anthropic_messages)
        if history_len == 0:
            #reminder拼接到第一条用户消息前面
            remind = build_user_context_reminder()
            user_message = f"{remind}\n\n{user_message}"
        
        self.anthropic_messages.append({
            "role":"user",
            "content":user_message
        })
        #agent loop循环

        for i in range(self.max_turns):
            #调用messagesapi
            response = self.call_anthropic(
                messages = self.anthropic_messages,
                tools=self.anthropic_tools
            )
            self.total_api_calls += 1

            #统计token消耗
            if response.usage is not None:
                self._record_usage(response.usage)

            self.anthropic_messages.append(
                response.model_dump(include={"role","content"})
            )
            #判断是否设计工具调用
            if response.stop_reason == "end_turn":
                for block in response.content:
                    if block.type == "text":
                        print(block.text)
                self.show_usage()
                self.turn_usage = TokenUsage()
                self.turn_cost_usd = 0.0
                return
            #涉及到工具调用，则先定义一个tool_result列表，然后for循环遍历block
            if response.stop_reason == "tool_use":
                tool_result = []
                for block in response.content:
                    #当block的type是tool_use,则解析，获取function_name，和arguments
                    if block.type == "tool_use":
                        function_name = block.name
                        arguments = block.input
                        call_id =  block.id
                #然后execute_tool()执行工具，得到result
                        try:
                            # 1. 展示工具调用
                            print_tool_call(function_name, arguments)
                            result = execute_tool(function_name,arguments)
                            # 3. 展示执行结果
                            print_tool_result(function_name, result)
                        except Exception as e:
                                result = f"Error: 工具执行失败：{e}"
                #把result消息拼接，装到tool_result列表
                        tool_result.append(
                            {
                                "type":"tool_result",
                                "tool_use_id":call_id,
                                "content":str(result)
                            }
                        )          
                #for遍历结束，把tool_result拼接到messages消息，然后tool_result清空
                if tool_result:
                    self.anthropic_messages.append({
                        "role":"user",
                        "content":tool_result
                    })
                    continue
                print("模型请求工具调用，但没有找到 tool_use 内容块")
                return                
            print(f"模型停止生成，原因：{response.stop_reason}")
            return
        print("超过最大调用次数！")         

        

    def _chat_openai(self,user_message):
        history_len = len(self.openai_messages)
        self.turn_count = 0
        # reminder拼接到第一条用户消息前面
        if history_len == 1:
            reminder = build_user_context_reminder()
            user_message = f"{reminder}\n\n{user_message}"

        self.openai_messages.append({"role": "user", "content": user_message})
        while True:
            self.turn_count += 1
            self.total_api_calls += 1
            if self.max_turns is not None and self.turn_count > self.max_turns:
                print(f"已达到最大轮数（{self.max_turns}），强制停止。")
                return
            
            try:
                response = self.call_openai(
                    messages = self.openai_messages,
                    tools= self.tools
                )
            except Exception as e:
                print(f"调用失败：",e)
                del self.openai_messages[history_len:]
                return
            
            if response.usage is not None:
                delta,cost = self._record_usage(response.usage)

            message = response.choices[0].message


            self.openai_messages.append(
                message.model_dump(exclude_none=True)
            )

            if not message.tool_calls:
                print("AI: ", message.content or "")
                self.show_usage()
                # 开始下一轮之前，清空本轮统计
                self.turn_usage = TokenUsage()
                self.turn_cost_usd = 0.0
                return
            
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                try:
                    arguments = json.loads(
                        tool_call.function.arguments
                    )
                except json.JSONDecodeError as e:
                    result =  f"Error: 工具参数 JSON 解析失败: {e}，请修正后重试"
                else:
                    try:
                        # 1. 展示工具调用
                        print_tool_call(function_name, arguments)
                        result = execute_tool(function_name,arguments)
                        # 3. 展示执行结果
                        print_tool_result(function_name, result)
                    except Exception as e:
                        result = f"Error: 工具执行失败：{e}"
                
                self.openai_messages.append(
                    {
                        "role":"tool",
                        "tool_call_id":tool_call.id,
                        "content":result
                    }
                )


    # ---------------- OpenAI 调用层 ----------------

    def call_openai(self, messages: list[dict], tools: list[dict] | None = None):
        """非流式调用 OpenAI 兼容接口，返回 SDK 原始 response。"""
        response = self.openai_client.chat.completions.create(
                    model = self.model,
                    messages=messages,
                    tools=tools,
                    stream=False,
                )
        return response

    def call_openai_stream(self, messages: list[dict], tools: list[dict] | None = None):
        """流式调用 OpenAI 兼容接口，返回 SDK 流迭代器。"""
        raise NotImplementedError

    # ---------------- Anthropic 调用层 ----------------

    def call_anthropic(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
    ):
        """非流式调用 Anthropic，返回 SDK 原始 response。
        system 为空时使用 self.system_prompt；请求需携带 max_tokens。
        """
        response = self.anthropic_client.messages.create(
            model = self.model,
            max_tokens= self.max_tokens,
            system = system or self.system_prompt,
            messages= messages,
            tools=tools
        )
        return response



    def call_anthropic_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
    ):
        """流式调用 Anthropic，返回 SDK 事件流迭代器。"""
        raise NotImplementedError


    def run(self):
        while True:
            user_message = input("User: ")

            if user_message.strip().lower() in ("exit",""):
                print("Bye!")
                break
            self.chat_once(user_message)
            self.auto_save()
                                    


if __name__ == "__main__":
    agent = Agent(
        provider="anthropic",
        api_base="https://api.deepseek.com/anthropic",
        api_key="***REMOVED***"
    )
    response = agent.call_anthropic(
         messages=[
        {
            "role": "user",
            "content": "你好，请介绍一下自己"
        }
    ]
    )
    for block in response.content:
        if block.type == "text":
            print(block.text)

