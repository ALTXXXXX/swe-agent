

from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()


class Agent:

    def __init__(self):
        #设置messages
        self.messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant"
            }
        ]

        #初始化大模型
        self.client = OpenAI(
            api_key = os.getenv("DEEPSEEK_API_KEY"),
            base_url = "https://api.deepseek.com",
        )

        #工具definitions
        self.tool_definitions = [
             {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获得指定地点的天气数据",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "要查询天气的地点"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
        
        #工具注册
        self.tool_registry = {
            "get_weather": self.get_weather
        }

    
    #执行天气查询的工具
    def get_weather(self,location):
        return f"当前{location}的天气是晴朗，25摄氏度"


    #执行工具
    def execute_tool(self,tool_call):
        try:
            function_name = tool_call.function.name
            arguments = json.loads(
                        tool_call.function.arguments
                    )
            function =  self.tool_registry.get(function_name)
            if function is None:
                return f"错误：不存在工具：{function_name}"
            result = function(**arguments)
            return str(result)

        except Exception as e:
            return f"工具执行失败： {e}"




    #处理一轮用户对话

    def chat_once(self,user_message):
        history_len = len(self.messages)
        self.messages.append({"role": "user", "content": user_message})
        while True:
            try:
                response = self.client.chat.completions.create(
                    model = "deepseek-flash",
                    messages=self.messages,
                    tools=self.tool_definitions,
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
                result = self.execute_tool(tool_call)
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
