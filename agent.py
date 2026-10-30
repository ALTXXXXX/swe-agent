

from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from session import save_session
from tools import tool_definitions,execute_tool
import uuid
import time
from typing import Callable, Awaitable
import os
import json
from prompt import build_static_system_prompt,build_dynamic_system_prompt,build_user_context_reminder


load_dotenv()


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
        self.max_cost_usd = max_cost_usd
        self.max_turns = max_turns
        self.confirm_fn = confirm_fn
        self.is_sub_agent = is_sub_agent    

        self.system_prompt = custom_system_prompt or (
            build_static_system_prompt() + build_dynamic_system_prompt()
        )

        self.tools = custom_tools if custom_tools is not None else tool_definitions

        if self.provider == "openai":
            self.client = OpenAI(
                api_key=api_key,
                base_url = api_base or "https://api.deepseek.com"
            )
        elif self.provider == "anthropic":
            raise NotImplementedError("Anthropic provider 尚未实现，请使用 OPENAI_API_KEY")
        else:
            raise ValueError(f"未知 provider: {provider}")
        
        #设置messages
        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt
            }
        ]
        self.session_id = uuid.uuid4().hex[:8]
        self.session_start_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        #运行时计数器（max_turns / max_cost_usd 靠它俩）
        self.turn_count = 0
        self.total_cost_usd = 0.0


    # #执行天气查询的工具
    # def get_weather(self,location):
    #     return f"当前{location}的天气是晴朗，25摄氏度"




    def _get_message_count(self) -> int:
        return len(self.messages)

    def auto_save(self) -> None:
        # chat的时候，把messages消息存放到json文件中
        save_session(self.session_id,{
            "metadata": { "id": self.session_id, "model": self.model,
                          "cwd": str(Path.cwd()), "startTime": self.session_start_time,
                          "messageCount": self._get_message_count() },
            "openaiMessages": self.messages if self.messages else None,
        })


    def restore_session(self,data: dict)-> None:
        if data.get("openaiMessages"): self.messages = data["openaiMessages"]
        #TODO anthropic messages之后补充







    def replay_history(self) -> None:
        """恢复会话后回放历史消息（跳过 system 和 tool 消息）"""
        for msg in self.messages:
            role = msg.get("role")
            content = msg.get("content") or ""
            if not content:
                continue
            if role == "user":
                print(f"User: {content}")
            elif role == "assistant":
                print(f"AI: {content}")
                    
    #处理一轮用户对话
    def chat_once(self,user_message):
        history_len = len(self.messages)
        self.turn_count = 0
        # reminder拼接到第一条用户消息前面
        if history_len == 1:
            reminder = build_user_context_reminder()
            user_message = f"{reminder}\n\n{user_message}"

        self.messages.append({"role": "user", "content": user_message})
        while True:
            self.turn_count += 1
            if self.max_turns is not None and self.turn_count > self.max_turns:
                print(f"已达到最大轮数（{self.max_turns}），强制停止。")
                return
            
            try:
                response = self.client.chat.completions.create(
                    model = self.model,
                    messages=self.messages,
                    tools=self.tools,
                    stream=False,
                )
            except Exception as e:
                print(f"调用失败：",e)
                del self.messages[history_len:]
                return
            message = response.choices[0].message
            self.messages.append(
                message.model_dump(exclude_none=True)
            )

            if not message.tool_calls:
                print("AI: ", message.content or "")
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
                        result = execute_tool(function_name,arguments)
                    except Exception as e:
                        result = f"Error: 工具执行失败：{e}"
                
                self.messages.append(
                    {
                        "role":"tool",
                        "tool_call_id":tool_call.id,
                        "content":result
                    }
                )
               

    def run(self):
        while True:
            user_message = input("User: ")

            if user_message.strip().lower() in ("exit",""):
                print("Bye!")
                break
            self.chat_once(user_message)
            self.auto_save()
                                    


if __name__ == "__main__":   
    agent = Agent()
    agent.run()
