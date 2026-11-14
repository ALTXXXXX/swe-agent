from pathlib import Path
from messages import Message

TASK_OUTPUT_DIR = Path.cwd() / ".mini-agent" / "task_outputs"
PREVIEW_CHARS = 2000 

def tool_result_budget(messages:list[Message], max_bytes=100_000):
    #取出messages最后一条消息；空历史直接返回
    if not messages:
        return messages
    last =  messages[-1]
    #收集tool_result，保存在一个元组中
    if not last.results:
        return messages
    blocks = [(i,b) for i, b in enumerate(last.results)]
    #遍历元组，判断内容长度是否超过max_bytes
    def size(b):
        c = b.content
        #按字节数计算（UTF-8），中文每字符占3字节，与 max_bytes 语义一致
        return len(c.encode("utf-8")) if isinstance(c,str) else len(str(c).encode("utf-8"))
    total = sum(size(b) for _,b in blocks)
    #不超过max_bytes，直接返回
    if total <= max_bytes:
        return messages
    #超过max_bytes，则从tool_result内容最大的开始，然后遍历
    ranked = sorted(blocks,key = lambda p: size(p[1]),reverse=True)
    for idx,block in ranked:
        if total <= max_bytes:
            break
        before = size(block)
        #小块落盘不划算（preview+包装文本可能比原文还大），跳过
        if before <= PREVIEW_CHARS * 2:
            continue
        block.content = persist_large_output(block.tool_call_id,block.content)
        total -= (before - size(block))
    
    return messages



def persist_large_output(tool_use_id, content):
    path = TASK_OUTPUT_DIR / f"{tool_use_id}.text"
    #确保目录存在，parents=True 连父目录一起创建，exist_ok=True 已存在时不报错
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content), encoding="utf-8")
    preview = str(content)[:PREVIEW_CHARS]
    return (f"<persisted-output path=\"{path}\">\n"
            f"{preview}\n...(truncated, full content at {path})\n"
            f"</persisted-output>")
    