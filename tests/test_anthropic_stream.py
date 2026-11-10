# tests/test_anthropic_stream.py
"""用伪造的 Anthropic 流验证流式工具执行链路：

- 文本增量正常回调
- tool_use 块的参数收齐后提前执行
- 提前执行的结果按 tool_use_id 回传，不会重复执行
- 非并发安全工具在流结束后执行
- 被权限拒绝的工具不执行
"""
import asyncio
import json
import time
from types import SimpleNamespace as NS

import pytest
from anthropic.types import Message

import agent as agent_mod
import tools


# ---------------- 构造伪造的流式事件 ----------------

def _event(kind, **kwargs):
    return NS(type=kind, **kwargs)


def _text_block(index, text):
    return [
        _event("content_block_start", index=index, content_block=NS(type="text")),
        _event(
            "content_block_delta",
            index=index,
            delta=NS(type="text_delta", text=text),
        ),
        _event("content_block_stop", index=index),
    ]


def _tool_block(index, tool_id, name, arguments):
    payload = json.dumps(arguments)
    chunks = [payload[: len(payload) // 2], payload[len(payload) // 2 :]]
    events = [
        _event(
            "content_block_start",
            index=index,
            content_block=NS(type="tool_use", id=tool_id, name=name),
        )
    ]
    events += [
        _event(
            "content_block_delta",
            index=index,
            delta=NS(type="input_json_delta", partial_json=chunk),
        )
        for chunk in chunks
    ]
    events.append(_event("content_block_stop", index=index))
    return events


def _message(msg_id, content, stop_reason):
    return Message.model_validate(
        {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": "fake",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )


class FakeStream:
    """anthropic AsyncMessageStream 的最小子集。"""

    def __init__(self, events, final_message, event_delay=0.0):
        self.events = events
        self.final_message = final_message
        self.event_delay = event_delay
        self.yielded_at = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for event in self.events:
            if self.event_delay:
                await asyncio.sleep(self.event_delay)
            self.yielded_at.append(time.perf_counter())
            yield event

    async def get_final_message(self):
        return self.final_message


class FakeClient:
    """按调用顺序返回预先准备好的 FakeStream。"""

    def __init__(self, streams):
        self._streams = list(streams)

    @property
    def messages(self):
        return self

    def stream(self, **kwargs):
        return self._streams.pop(0)


class Captured:
    def __init__(self):
        self.texts = []
        self.tool_calls = []
        self.tool_results = []


@pytest.fixture
def ui(monkeypatch):
    """静音并捕获 UI 输出。"""
    cap = Captured()
    monkeypatch.setattr(agent_mod, "print_text_delta", cap.texts.append)
    monkeypatch.setattr(
        agent_mod,
        "print_tool_call",
        lambda name, args: cap.tool_calls.append((name, args)),
    )
    monkeypatch.setattr(
        agent_mod,
        "print_tool_result",
        lambda name, result: cap.tool_results.append((name, result)),
    )
    return cap


def _make_agent(monkeypatch, streams):
    agent = agent_mod.Agent(
        provider="anthropic", api_key="fake", api_base="http://fake"
    )
    monkeypatch.setattr(agent, "anthropic_client", FakeClient(streams))
    monkeypatch.setattr(agent, "show_usage", lambda: None)
    return agent


def _run(coro):
    return asyncio.run(coro)


# ---------------- 用例 ----------------

def test_call_anthropic_stream_delivers_text_and_parsed_tool_input(
    monkeypatch, ui
):
    final = _message(
        "msg_1",
        [
            {"type": "text", "text": "你好"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_file",
                "input": {"file_path": "a.txt"},
            },
        ],
        "tool_use",
    )
    stream = FakeStream(
        [_event("message_start", message=None)]
        + _text_block(0, "你好")
        + _tool_block(1, "toolu_1", "read_file", {"file_path": "a.txt"})
        + [_event("message_stop")],
        final,
    )
    agent = _make_agent(monkeypatch, [stream])

    tool_blocks = []

    async def on_tool(block):
        tool_blocks.append(block)

    result = _run(
        agent.call_anthropic_stream(
            messages=[],
            tools=[],
            on_text=ui.texts.append,
            on_tool_block_complete=on_tool,
        )
    )

    assert ui.texts == ["你好"], "文本增量没有送达"
    assert tool_blocks == [
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "read_file",
            "input": {"file_path": "a.txt"},
        }
    ], "tool_use 参数没有在块结束时解析出来"
    assert result.id == "msg_1"


def test_safe_tools_execute_early_and_only_once(monkeypatch, tmp_path, ui):
    f1 = tmp_path / "a.txt"
    f1.write_text("AAA")
    f2 = tmp_path / "b.txt"
    f2.write_text("BBB")

    original_read = tools.tool_handlers["read_file"]
    calls = []
    started_at = []

    def counting_read(file_path):
        calls.append(file_path)
        started_at.append(time.perf_counter())
        time.sleep(0.15)  # 模拟耗时，让工具执行和流式生成重叠
        return original_read(file_path)

    monkeypatch.setitem(tools.tool_handlers, "read_file", counting_read)

    msg1 = _message(
        "msg_1",
        [
            {"type": "text", "text": "读取中"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_file",
                "input": {"file_path": str(f1)},
            },
            {
                "type": "tool_use",
                "id": "toolu_2",
                "name": "read_file",
                "input": {"file_path": str(f2)},
            },
        ],
        "tool_use",
    )
    msg2 = _message("msg_2", [{"type": "text", "text": "完成"}], "end_turn")

    stream1 = FakeStream(
        [_event("message_start", message=None)]
        + _text_block(0, "读取中")
        + _tool_block(1, "toolu_1", "read_file", {"file_path": str(f1)})
        + _tool_block(2, "toolu_2", "read_file", {"file_path": str(f2)})
        + [_event("message_stop")],
        msg1,
        event_delay=0.02,
    )
    stream2 = FakeStream(
        [_event("message_start", message=None)]
        + _text_block(0, "完成")
        + [_event("message_stop")],
        msg2,
    )

    agent = _make_agent(monkeypatch, [stream1, stream2])
    _run(agent._chat_anthropic_stream("读这两个文件"))

    # 每个工具只执行一次（不能因为提前执行 + 事后收集而跑两遍）
    assert len(calls) == 2
    assert sorted(calls) == sorted([str(f1), str(f2)])

    # tool_result 按最终消息里的 tool_use 顺序回传
    tool_message = agent.anthropic_messages[2]
    assert tool_message["role"] == "user"
    assert [r["tool_use_id"] for r in tool_message["content"]] == [
        "toolu_1",
        "toolu_2",
    ]
    assert all(r["type"] == "tool_result" for r in tool_message["content"])

    # 提前执行：第一个工具在第一轮流结束前就已经启动
    assert started_at[0] < max(stream1.yielded_at), "工具没有和模型生成重叠"

    # 文本增量没有丢
    assert "读取中" in ui.texts
    assert "完成" in ui.texts


def test_non_safe_tool_executes_after_stream(monkeypatch, ui):
    original_weather = tools.tool_handlers["get_weather"]
    calls = []

    def counting_weather(location):
        calls.append(location)
        return original_weather(location)

    monkeypatch.setitem(tools.tool_handlers, "get_weather", counting_weather)

    msg1 = _message(
        "msg_1",
        [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "get_weather",
                "input": {"location": "北京"},
            }
        ],
        "tool_use",
    )
    msg2 = _message("msg_2", [{"type": "text", "text": "ok"}], "end_turn")
    stream1 = FakeStream(
        [_event("message_start", message=None)]
        + _tool_block(0, "toolu_1", "get_weather", {"location": "北京"})
        + [_event("message_stop")],
        msg1,
    )
    stream2 = FakeStream(
        [_event("message_start", message=None)]
        + _text_block(0, "ok")
        + [_event("message_stop")],
        msg2,
    )

    agent = _make_agent(monkeypatch, [stream1, stream2])
    _run(agent._chat_anthropic_stream("查天气"))

    assert calls == ["北京"], "非并发安全工具应该执行一次"
    content = agent.anthropic_messages[2]["content"]
    assert content[0]["tool_use_id"] == "toolu_1"
    assert "晴朗" in content[0]["content"]


def test_truncated_stream_answers_tool_use_without_executing(monkeypatch, ui):
    """生成被截断（stop_reason=max_tokens）时：
    不执行工具，但必须补一条 tool_result，保证历史合法。
    """
    original_write = tools.tool_handlers["write_file"]
    calls = []

    def counting_write(file_path, content):
        calls.append(file_path)
        return original_write(file_path, content)

    monkeypatch.setitem(tools.tool_handlers, "write_file", counting_write)

    msg1 = _message(
        "msg_1",
        [
            {
                "type": "tool_use",
                "id": "toolu_cut",
                "name": "write_file",
                "input": {"file_path": "x.txt", "content": "partial"},
            }
        ],
        "max_tokens",
    )
    msg2 = _message("msg_2", [{"type": "text", "text": "ok"}], "end_turn")

    stream1 = FakeStream(
        [_event("message_start", message=None)]
        + _tool_block(
            0,
            "toolu_cut",
            "write_file",
            {"file_path": "x.txt", "content": "partial"},
        )
        + [_event("message_stop")],
        msg1,
    )
    stream2 = FakeStream(
        [_event("message_start", message=None)]
        + _text_block(0, "ok")
        + [_event("message_stop")],
        msg2,
    )

    agent = _make_agent(monkeypatch, [stream1, stream2])
    _run(agent._chat_anthropic_stream("写文件"))

    assert calls == [], "被截断的工具调用不应执行"

    assistant_index = next(
        i
        for i, message in enumerate(agent.anthropic_messages)
        if message["role"] == "assistant"
        and any(
            block.get("type") == "tool_use"
            for block in message["content"]
        )
    )
    result_message = agent.anthropic_messages[assistant_index + 1]
    assert result_message["role"] == "user"
    first_block = result_message["content"][0]
    assert first_block["type"] == "tool_result"
    assert first_block["tool_use_id"] == "toolu_cut"
    assert "未完成" in first_block["content"]


def test_repair_history_fills_missing_tool_results(monkeypatch):
    """历史中断在 tool_use 上时，修复逻辑要补出合法的 tool_result。"""
    agent = _make_agent(monkeypatch, [])
    agent.anthropic_messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "write_file",
                    "input": {},
                }
            ],
        },
        {"role": "user", "content": "继续"},
    ]

    agent._repair_anthropic_history()

    repaired = agent.anthropic_messages[2]["content"]
    assert repaired[0]["type"] == "tool_result"
    assert repaired[0]["tool_use_id"] == "toolu_1"
    assert repaired[1] == {"type": "text", "text": "继续"}

    # 再修一次不应重复插入
    agent._repair_anthropic_history()
    assert len(agent.anthropic_messages) == 3

    # 悬空在历史结尾：直接补一条 user 消息
    agent.anthropic_messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "write_file",
                    "input": {},
                }
            ],
        },
    ]
    agent._repair_anthropic_history()

    tail = agent.anthropic_messages[-1]
    assert tail["role"] == "user"
    assert tail["content"][0]["tool_use_id"] == "toolu_2"


def test_denied_safe_tool_is_not_executed(monkeypatch, tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("AAA")

    original_read = tools.tool_handlers["read_file"]
    calls = []

    def counting_read(file_path):
        calls.append(file_path)
        return original_read(file_path)

    monkeypatch.setitem(tools.tool_handlers, "read_file", counting_read)

    msg1 = _message(
        "msg_1",
        [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "read_file",
                "input": {"file_path": str(f)},
            }
        ],
        "tool_use",
    )
    msg2 = _message("msg_2", [{"type": "text", "text": "ok"}], "end_turn")
    stream1 = FakeStream(
        [_event("message_start", message=None)]
        + _tool_block(0, "toolu_1", "read_file", {"file_path": str(f)})
        + [_event("message_stop")],
        msg1,
    )
    stream2 = FakeStream(
        [_event("message_start", message=None)]
        + _text_block(0, "ok")
        + [_event("message_stop")],
        msg2,
    )

    agent = _make_agent(monkeypatch, [stream1, stream2])
    monkeypatch.setattr(
        agent, "_check_permission", lambda name, args: (False, "blocked")
    )

    _run(agent._chat_anthropic_stream("读文件"))

    assert calls == [], "被拒绝的工具不应执行"
    content = agent.anthropic_messages[2]["content"]
    assert content[0]["tool_use_id"] == "toolu_1"
    assert "blocked" in content[0]["content"]
