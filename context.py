import json
import time
from pathlib import Path
from messages import Message, Text, ToolCall, ToolResult, message_to_dict

TASK_OUTPUT_DIR = Path.cwd() / ".mini-agent" / "task_outputs"
TRANSCRIPT_DIR = Path.cwd() / ".mini-agent" / "transcripts"
PREVIEW_CHARS = 2000
KEEP_RECENT_TOOL_RESULTS = 5

# ---- 上下文压缩（最小版）----
CONTEXT_WINDOW = 1_048_576
COMPACT_TRIGGER_TOKENS = int(CONTEXT_WINDOW * 0.70)   # 约 734K
COMPACT_KEEP_RECENT_TURNS = 6
MAX_COMPACT_FAILURES = 3
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
    

def collect_tool_result_blocks(messages: list[Message]) -> list[ToolResult]:
    block = []
    for message in messages:
        block.extend(message.results)
    return block

def micro_compact(messages: list[Message], keep = KEEP_RECENT_TOOL_RESULTS) -> list[Message]:
    tool_results = collect_tool_result_blocks(messages)
    if len(tool_results) <= keep:
        return messages
    
    for block in tool_results[:-keep]:
        content = block.content
        if len(content) <= 120:
            continue
        if content.startswith("<persisted-output path=\""):
            # 已落盘：保留文件路径，压缩后仍能定位全文
            path = content.split('"',2)[1]
            block.content = f"[Earlier tool result compacted. Full content at {path}]"
        else:
            block.content = "[Earlier tool result compacted. Re-run if needed.]"
    return messages


SUMMARY_SYSTEM_PROMPT = """你是上下文压缩器。请把下面的 Agent 对话记录压缩成结构化摘要，供后续继续工作。
必须保留：用户目标与约束、已完成的修改（文件路径与要点）、重要发现、已执行的关键命令及结论、未完成工作和下一步。
不要编造事实，只输出摘要正文，不要调用任何工具。"""


def estimate_tokens(messages: list[Message]) -> int:
    """粗估 token：中文约 1.5 字/token，英文约 4 字符/token，取折中 2.5。"""
    chars = 0
    for message in messages:
        for part in message.parts:
            if isinstance(part, Text):
                chars += len(part.text)
            elif isinstance(part, ToolCall):
                chars += len(part.name) + len(part.raw_arguments)
            elif isinstance(part, ToolResult):
                chars += len(part.content)
    return int(chars / 2.5)


def is_turn_start(messages: list[Message], index: int) -> bool:
    """一轮对话的起点：带文本的 user 消息，且上一条是不含工具调用的 assistant。"""
    message = messages[index]
    if message.role != "user" or not message.text():
        return False
    if index == 0:
        return True
    previous = messages[index - 1]
    return previous.role == "assistant" and not previous.tool_calls


def compact_keep_index(messages: list[Message], keep_turns: int) -> int | None:
    """保留区起点；轮数不够则返回 None（不压缩）。"""
    starts = [i for i in range(len(messages)) if is_turn_start(messages, i)]
    if len(starts) <= keep_turns:
        return None
    return starts[-keep_turns]


def render_transcript(messages: list[Message]) -> str:
    """IR -> 纯文本，作为摘要请求的输入。"""
    lines = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, Text):
                lines.append(f"[{message.role}] {part.text}")
            elif isinstance(part, ToolCall):
                lines.append(f"[tool_call {part.name}] {part.raw_arguments}")
            elif isinstance(part, ToolResult):
                lines.append(f"[tool_result {part.tool_call_id}]\n{part.content}")
    return "\n\n".join(lines)


def write_transcript(session_id: str, messages: list[Message]) -> Path:
    """压缩前把完整历史落盘（JSONL），保证可追溯。"""
    path = TRANSCRIPT_DIR / f"{session_id}-{int(time.time())}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for message in messages:
            f.write(json.dumps(message_to_dict(message), ensure_ascii=False) + "\n")
    return path




