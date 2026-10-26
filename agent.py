

from openai import OpenAI
from dotenv import load_dotenv
from tools import tool_definitions,execute_tool
import os
import json


load_dotenv()


class Agent:

    def __init__(self):
        #设置messages
        self.messages = [
            {
                "role": "system",
                "content": f"You are a coding assistant. Current working directory: {os.getcwd()}. "
                   f"Use relative paths or absolute paths under this directory."
            }
        ]

        #初始化大模型
        self.client = OpenAI(
            api_key = os.getenv("DEEPSEEK_API_KEY"),
            base_url = "https://api.deepseek.com",
        )  




    # #执行天气查询的工具
    # def get_weather(self,location):
    #     return f"当前{location}的天气是晴朗，25摄氏度"






    #处理一轮用户对话
    def chat_once(self,user_message):
        history_len = len(self.messages)
        self.messages.append({"role": "user", "content": user_message})
        while True:
            try:
                response = self.client.chat.completions.create(
                    model = "deepseek-flash",
                    messages=self.messages,
                    tools=tool_definitions,
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
                arguments = json.loads(
                    tool_call.function.arguments
                )
                result = execute_tool(function_name,arguments)
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
                                    


if __name__ == "__main__":
    agent = Agent()
    agent.run()
