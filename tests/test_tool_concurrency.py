# tests/test_tool_concurrency.py
"""验证 execute_tool 真的在 worker 线程里跑、能并行、且不阻塞事件循环。"""
import asyncio
import threading
import time

import tools


def _run(coro):
    return asyncio.run(coro)


def test_execute_tool_runs_in_worker_thread(monkeypatch):
    """工具不能在事件循环的 MainThread 里同步执行。"""
    seen = []

    def probe():
        seen.append(threading.current_thread().name)
        return "ok"

    monkeypatch.setitem(tools.tool_handlers, "_probe", probe)

    assert _run(tools.execute_tool("_probe", {})) == "ok"
    assert seen, "工具没有被执行"
    assert seen[0] != "MainThread", f"工具跑在事件循环线程里: {seen[0]}"
    assert seen[0].startswith("asyncio_"), f"不是 asyncio 默认线程池的线程: {seen[0]}"


def test_tools_run_in_parallel(monkeypatch):
    """多个工具同时在跑：记录最大并发数，并检查总耗时远小于串行。"""
    lock = threading.Lock()
    state = {"active": 0, "max_active": 0}
    delay = 0.2

    def slow(x):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            time.sleep(delay)
        finally:
            with lock:
                state["active"] -= 1
        return x

    monkeypatch.setitem(tools.tool_handlers, "_slow", slow)

    async def run():
        return await asyncio.gather(
            *[tools.execute_tool("_slow", {"x": i}) for i in range(4)]
        )

    t0 = time.perf_counter()
    results = _run(run())
    elapsed = time.perf_counter() - t0

    assert results == ["0", "1", "2", "3"]
    assert state["max_active"] >= 2, "工具没有并发执行"
    # 串行需要 4 * 0.2 = 0.8s，这里留出充足余量
    assert elapsed < 0.7, f"4 个 {delay}s 的工具耗时 {elapsed:.2f}s，看起来是串行"


def test_event_loop_stays_responsive(monkeypatch):
    """工具执行期间心跳协程仍在推进，说明事件循环没有被阻塞。"""
    def slow():
        time.sleep(0.2)
        return "ok"

    monkeypatch.setitem(tools.tool_handlers, "_slow", slow)

    async def run():
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        task = asyncio.create_task(heartbeat())
        try:
            await tools.execute_tool("_slow", {})
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return ticks

    assert _run(run()) >= 3, "心跳没有推进，事件循环被阻塞了"
