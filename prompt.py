from ntpath import isfile
import os
import platform
from datetime import date

from pathlib import Path
import subprocess
STATIC_CORE = """你是Mini Claude Code，一个小型的代码助手命令行界面。
你利用手头可用的工具协助完成软件工程任务。
# 完成任务
 - 不要对未阅读过的代码提出修改建议。请先阅读文件。
 除非必要，否则不要创建新文件。优先编辑现有文件。
 避免过度设计，仅实施所要求的变更。
谨慎执行操作
 优先选择可逆操作。对于风险性或破坏性操作（如rm -rf、git push，
 在删除表之前，请先与用户确认。
# 使用你的工具
 使用read_file / edit_file / list_files / grep_search替代shell cat命令，
 sed、ls、grep。保留run_shell用于实际的shell操作。
 若多个工具调用相互独立，可并行执行。
# 语气与风格
 - 回答要简洁明了。先给出答案。
 参考代码格式为文件路径:行号。"""

def build_static_system_prompt() -> str:
    """静态核心，agent的人和行为准则，基本不变"""
    return STATIC_CORE



#加动态环境信息
def build_dynamic_system_prompt() -> str:
    #动态环境，每次重启的时候都会调用，因为工作目录，环境状态可能改变
    plat = f"{platform.system()} {platform.machine()}"
    shell = os.environ.get("SHELL") or os.environ.get("ComSpec", "cmd.exe")
    return (
        f"\n# Environment\n"
        f"Working directory: {Path.cwd()}\n"
        f"Platform: {plat}\n"
        f"Shell: {shell}\n"
        f"{get_git_context()}\n"
    )
def _decode_output(data: bytes) -> str:
    """和 tools.py 里的同款思路：先 utf-8 再 gbk，最后兜底"""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")

def get_git_context() -> str:
    """注入 Git 状态：当前分支、最近 5 条提交、未提交的改动"""
    try:
        opts = {"capture_output": True, "timeout": 3}
        branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], **opts
            )
        log = subprocess.run(
                ["git", "log", "--oneline", "-5"], **opts
            )
        status = subprocess.run(
                ["git", "status", "--short"], **opts
            )
        # 三个命令都可能因为不在 git 仓库里而失败，分别处理
        parts = []
        if branch.returncode == 0:
            parts.append(f"Git branch: {_decode_output(branch.stdout).strip()}")
        if log.returncode == 0:
            log_text = _decode_output(log.stdout).strip()
            if log_text:
                parts.append(f"Recent commits:\n{log_text}")
        if status.returncode == 0:
            status_text = _decode_output(status.stdout).strip()
            if status_text:
                parts.append(f"Git status:\n{status_text}")
        
        if not parts:
            return ""
        return "\n" + "\n".join(parts)
    except Exception:
        return "" #git没装或者超时了，默认失败


def load_agents_md() -> str:
    """多级扫描：从 cwd 一路向上找 AGENTS.md，近的覆盖远的"""
    parts: list[str] = []
    d = Path.cwd().resolve()
    while True:
        f = d / "AGENTS.md"
        if f.is_file():
            try:
                content =  f.read_text(encoding="utf-8")
                parts.insert(0,content) #头插法
            except Exception:
                pass
        parent = d.parent
        if parent == d:
            break
        d = parent
    
    if not parts:
        return ""
    return "\n\n--\n\n".join(parts)

def build_user_context_reminder() -> str:
    """user 消息里的提醒：AGENTS.md 内容 + 今天的日期"""
    agents_md = load_agents_md()
    today = date.today().isoformat()
    reminder = "<system-reminder>\n"
    if agents_md:
        reminder += f"\n{agents_md}\n\n"
    reminder += f"# currentDate\nToday's date is {today}.\n"
    reminder += "</system-reminder>"
    return reminder