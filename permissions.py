"""permissions.py"""
from __future__ import annotations
import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import indent

#定义工作目录
# tools.py
DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s"),
    re.compile(r"\bgit\s+(push|reset|clean|checkout\s+\.)"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s"),
    re.compile(r">\s*/dev/"),
    re.compile(r"\bkill\b"),
    re.compile(r"\bpkill\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\bdel\s", re.IGNORECASE),
    re.compile(r"\brmdir\s", re.IGNORECASE),
    re.compile(r"\bformat\s", re.IGNORECASE),
    re.compile(r"\btaskkill\s", re.IGNORECASE),
    re.compile(r"\bRemove-Item\s", re.IGNORECASE),
    re.compile(r"\bStop-Process\s", re.IGNORECASE),
]
READ_TOOLS = {"read_file", "list_files", "grep_search", "web_fetch"}
EDIT_TOOLS = {"write_file", "edit_file"}

_cached_rules: dict | None = None

def is_dangerous(command: str) -> bool:
   return any(p.search(command) for p in DANGEROUS_PATTERNS)



# tools.py


def _parse_rule(rule: str) -> dict:
    m = re.match(r"^([a-z_]+)\((.+)\)$", rule)
    if m:
        return {"tool":m.group(1), "pattern":m.group(2)}
    return {"tool":rule, "pattern":None}


def _load_settings(file_path: Path)-> dict | None:
    if not file_path.exists():
        return None
    try:
        return json.loads(file_path.read_text())
    except Exception:
        return None



def load_permission_rules() -> dict:
    global _cached_rules
    if _cached_rules is not None:
        return _cached_rules
    allow: list[dict] = []
    deny: list[dict] = []

    user_settings = _load_settings(Path.home() / ".mini-agent" / "settings.json")
    project_settings = _load_settings(Path.cwd() / ".mini-agent" / "settings.json")

    for settings in [user_settings,project_settings]:
        if not settings or "permissions" not in settings:
             continue
        perms = settings["permissions"]
        for perm in perms.get("allow",[]):
            allow.append(_parse_rule(perm))
        for perm in perms.get("deny",[]):
            deny.append(_parse_rule(perm))
    
    _cached_rules = {"allow":allow, "deny":deny}
    return _cached_rules
    

def _matches_rule(
    rule: dict,
    tool_name: str,
    inp: dict
) -> bool:

    if rule["tool"] != tool_name:
        return False

    if rule["pattern"] is None:
        return True
    
    value = ""
    
    if rule["tool"] == "run_shell":
        value = inp.get("command","")
    elif "file_path" in inp:
        value = inp.get("file_path")
    else:
        return True

    pattern = rule["pattern"]

    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return value == pattern

    
    


def _check_permission_rules(tool_name: str, inp: dict) -> str | None:
    rules = load_permission_rules()

    for rule in rules["deny"]:
        if _matches_rule(rule,tool_name,inp):
            return "deny"
    
    for rule in rules["allow"]:
        if _matches_rule(rule,tool_name,inp):
            return "allow"
    return None



def chek_permission(
    tool_name: str,
    inp: dict,
    mode: str = "default",
    plan_file_path: str | None = None
):
    """Return {"action":"allow"|"deny"|"confirm", "message": "..." }"""
    #Layer1 配置文件规则，加载用户配置的rules，然后判断是deny还是allow
    rule_result = _check_permission_rules(tool_name,inp)
    if rule_result == "deny":
        return {"action": "deny", "message": f"Denied by permission rule for {tool_name}"}
    #Layer2 权限模式检查，读工具永远放行，plan拦截修改/shell命令 
    #acceptEdit对于编辑直接通行。bypassPermmissions（yolo）遇到了直接通过
    
    if mode == "plan":
        if tool_name in EDIT_TOOLS:
            file_path = inp.get("file_path") or inp.get("path")
            if plan_file_path and file_path == plan_file_path:
                return {"action":"allow"}
            return {"action": "deny", "message": f"Blocked in plan mode: {tool_name}"}

        if tool_name == "run_shell":
            return {"action":"deny","message":"Shell commands blocked in plan mode"}
    
    if mode == "bypassPermissions":
        return {"action":"allow"}
    
    if mode == "acceptEdits" and tool_name in EDIT_TOOLS:
        return {"action":"allow"}
    
    if rule_result == "allow":
        return {"action": "allow"}

    if tool_name in READ_TOOLS:
        return {"action": "allow"}

    if tool_name in ("enter_plan_mode", "exit_plan_mode"):
        return {"action": "allow"}

    
    # Layer 3 内置危险模式检查，比如shell命令是否在危险正则表达式
    #写或者编辑命令需要confirm，同时把他的input也得展示出来
    need_confirm = False
    confirm_message = ""
    if tool_name == "run_shell" and is_dangerous(inp.get("command","")):
        need_confirm = True
        confirm_message = inp.get("command","")
    elif tool_name == "write_file" and not Path(inp.get("file_path","")).exists():
        need_confirm = True
        confirm_message = f"write new file: {inp.get('file_path', '')}"
    elif tool_name == "edit_file" and not Path(inp.get("file_path","")).exists():
        need_confirm = True
        confirm_message = f"edit non-existent file: {inp.get('file_path', '')}"
    
    if need_confirm:
        if mode == "dontAsk":
            return {"action": "deny", "message": f"Auto-denied (dontAsk mode): {confirm_message}"}
    
        return {"action": "confirm", "message": confirm_message}
    return {"action":"allow"}


    
