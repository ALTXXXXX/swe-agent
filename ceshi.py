import asyncio
from anthropic import AsyncAnthropic


async def main():
    async with client.messages.stream(
        model="deepseek-flash",
        max_tokens=1024,
        messages=[
            {"role":"user","content":"介绍一下python"}
        ]
    )as stream:
        final_message = await stream.get_final_message()
        print("完整响应：")
        print(final_message)

asyncio.run(main())
