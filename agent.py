# from openai import OpenAI
# from dotenv import load_dotenv
# import os

# load_dotenv()

# api_key = os.getenv("DEEPSEEK_API_KEY")

# client = OpenAI(
#     api_key = api_key,
#     base_url = "https://api.deepseek.com",
# )


# messages = [
#     {"role": "system", "content": "You are a helpful assistant"},
# ]


# def chatOnce(user_message):
#         messages.append({"role": "user", "content": user_message})
#         try:
#             response = client.chat.completions.create(
#             model = "deepseek-flash",
#             messages=messages,
#             stream=False,
#             )
#             answer = response.choices[0].message.content
#             print("AI: "+ answer)
#             messages.append({"role": "assistant", "content": answer})
#         except Exception as e:
#             print(f"Error: {e}")
#             messages.pop()

# def chat():
#     while True:
#         user_message = input("User: ")
#         if user_message == "exit" or user_message == "":
#             print("Bye!")
#             messages.clear()
#             break
#         chatOnce(user_message)
        


# chat()

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

messages = [
    {"role": "system", "content": "You are a helpful assistant"},
]
client = OpenAI(
    api_key = os.getenv("DEEPSEEK_API_KEY"),
    base_url = "https://api.deepseek.com",
)

response = client.chat.completions.create(
    model = "deepseek-flash",
    messages=messages,
    stream=False,
)

def chatOnce(user_message):
    messages.append({"role": "user", "content": user_message})
    try:
        response = client.chat.completions.create(
            model = "deepseek-flash",
            messages=messages,
            stream=False,
        )
        answer = response.choices[0].message.content
        print("AI: " + answer)
        messages.append({"role": "assistant", "content": answer})
    except Exception as e:
        print(f"调用失败： {e}")
        messages.pop()


def chat():
    while True:
        user_message = input("User: ")
        if user_message.strip().lower() == "exit" or user_message.strip() == "":
            print("Bye!")
            messages = messages[1:]
            break
        chatOnce(user_message)

chat()