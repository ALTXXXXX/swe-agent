import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(override=True)
print("OPENAI_API_KEY:", bool(os.environ.get("OPENAI_API_KEY")))
print("ANTHROPIC_API_KEY:", bool(os.environ.get("ANTHROPIC_API_KEY")))
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL")
)

response = client.messages.create(
    model="deepseek-flash",
    max_tokens=1000,
    messages=[
        {"role": "user", "content": "你好"}
    ]
)

print(response.content)