
# ui.py
from rich.console import Console
from rich.text import Text


console = Console()


# 工具图标映射
TOOL_ICONS = {
    "read_file": "📖",
    "write_file": "✏️",
    "edit_file": "📝",
    "list_files": "📂",
    "grep_search": "🔍",
    "run_shell": "💻",
}


def _get_tool_icon(name: str) -> str:
    """根据工具名称获取图标。"""
    return TOOL_ICONS.get(name, "🔧")


def _get_tool_summary(name: str, inp: dict) -> str:
    """提取工具参数中的关键信息。"""

    # 文件操作
    if "file_path" in inp:
        return str(inp["file_path"])

    # Shell 命令
    if "command" in inp:
        return str(inp["command"])

    # 搜索关键词
    if "pattern" in inp:
        return str(inp["pattern"])

    return ""


def print_tool_call(name: str, inp: dict) -> None:
    """展示工具调用信息。"""

    icon = _get_tool_icon(name)
    summary = _get_tool_summary(name, inp)

    line = Text()
    line.append(f"  {icon} {name}", style="yellow")

    if summary:
        line.append(f"  {summary}", style="dim")

    console.print(line)


def _summarize_result(name: str, result: str) -> str:
    """根据不同工具，生成适合终端展示的结果摘要。"""

    result = str(result)

    if name in ("write_file", "edit_file"):
        # 写入和编辑：只显示操作结果的第一行
        lines = result.splitlines()
        return lines[0] if lines else "操作完成"

    elif name == "read_file":
        # 读取文件：不展示完整文件内容
        return f"已读取文件 ({len(result)} chars)"

    elif name == "list_files":
        # 文件列表：显示数量和少量内容
        lines = result.splitlines()
        preview = "\n".join(lines[:3])

        if len(lines) > 3:
            preview += f"\n... 还有 {len(lines) - 3} 行"

        return preview or "没有找到文件"

    elif name == "grep_search":
        # 搜索结果：只显示少量匹配内容
        lines = result.splitlines()
        preview = "\n".join(lines[:3])

        if len(lines) > 3:
            preview += f"\n... 还有 {len(lines) - 3} 条结果"

        return preview or "没有找到匹配内容"

    elif name == "run_shell":
        # Shell：保留实际执行输出，但限制长度
        max_len = 300

        if len(result) > max_len:
            return result[:max_len] + f"\n... ({len(result)} chars total)"

        return result or "命令执行完成"

    else:
        # 其他工具：通用截断
        max_len = 200

        if len(result) > max_len:
            return result[:max_len] + f"\n... ({len(result)} chars total)"

        return result or "执行完成"


def print_text_delta(text: str) -> None:
    """流式输出文本增量。禁用 markup/highlight，避免模型输出被 rich 解析。"""
    if not text:
        return
    console.print(text, end="", markup=False, highlight=False)
    console.file.flush()


def print_tool_result(name: str, result: str) -> None:
    """展示工具执行结果摘要。"""

    summary = _summarize_result(name, result)

    # 每行添加缩进，形成工具调用的层级效果
    lines = summary.splitlines()

    for line in lines:
        console.print(f"    [dim]└─ {line}[/dim]")


