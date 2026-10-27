import json
from math import trunc
from nt import error
from pathlib import Path
import subprocess
import re
import html
import urllib.request
import urllib.error

from sys import stdout
tool_definitions = [
    {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "获得指定地点的天气数据",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "要查询天气的地点"
                                }
                            },
                            "required": ["location"]
                        }
                    }
    },
    {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "读取指定路径的文本文件",
                        "parameters":{
                            "type": "object",
                            "properties":{
                                "file_path": {
                                    "type": "string",
                                    "description": "需要读取的文件路径"
                                }
                            },
                            "required":["file_path"]

                        }


                    }
    },
    {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "Edit a file by replacing a unique occurrence of old text with new text. The old_string must exist in the file and appear exactly once.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path of the file to edit."
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find in the file. It must exist and appear only once."
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text."
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "将内容写入指定文件。文件不存在则自动创建（含父目录）；已存在则整体覆盖原内容。适合创建新文件或重写整个文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "目标文件路径，相对当前工作目录或绝对路径"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的完整文件内容"
                }
            },
            "required": ["file_path", "content"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "列出指定目录下的所有文件和子目录名称。用于了解项目结构、查找文件位置。返回结果中目录前有 [dir] 标识。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要列出内容的目录路径，\".\" 表示当前工作目录"
                }
            },
            "required": ["file_path"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": "执行系统 shell 命令并返回输出。Windows 下使用 cmd.exe 语法。谨慎使用删除/格式化等破坏性命令。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 30"
                }
            },
            "required": ["command"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "grep_search",
        "description": "在指定目录下递归搜索文本内容，返回匹配的文件路径、行号和该行内容。用于定位代码位置、查找某个函数或变量的定义与用法。结果最多返回 100 行。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "要搜索的文本内容"
                },
                "path": {
                    "type": "string",
                    "description": '搜索的起始目录，默认为当前工作目录 "."'
                },
                "include": {
                    "type": "string",
                    "description": '只搜索匹配该模式的文件，如 "*.py" 只搜 Python 文件'
                }
            },
            "required": ["pattern"]
        }
    }
},
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "抓取一个网页 URL 并返回其文本内容。HTML 页面会自动去除标签只留正文。用于查文档、看网页内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的完整 URL，必须以 http:// 或 https:// 开头"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "返回内容的最大字符数，默认 50000"
                    }
                },
                "required": ["url"]
            }
        }
    },
 

]
#执行天气查询的工具
def get_weather(inp: dict) -> str:
    location = inp["location"]
    return f"当前{location}的天气是晴朗，25摄氏度"



def _read_file(inp: dict) -> str:
    
    try:
        content = Path(inp["file_path"]).read_text()
        lines = content.splitlines()
        numbered = "\n".join(
        f"{i+1:4d} | {line}" for i, line in enumerate(lines)
        )
        return numbered
    except Exception as e:
        return f"错误的文件读取：{e}"


def _web_fetch(inp: dict) -> str:
    url = inp["url"]
    max_length = inp.get("max_length",50000)
    if not url.startswith(("http://", "https://")):
        return f"Error: only http/https is supported, got: {url}"
    
    try:
        req = urllib.request.Request(url,headers={"User-Agent": "my-sweagent/0.1"})
        with urllib.request.urlopen(req,timeout=30) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type","")
            raw = resp.read()    
    except urllib.error.HTTPError as e:
        return f"HTTP error: {e.code} {e.reason}"
    except Exception as e:
        return f"Error fetching {url}: {e}"

    #对raw进行解析，先按照utf-8，不行就gbk  
    try:

        text =  raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            text = raw.decode("utf-8",errors="replace")
    
    #数据清洗，剥脚本/样式 → 标签变空格 → 实体还原 → 压缩空
    if "html" in content_type.lower():
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        
    
    #判断文本大小，大于maxLength就截断
    if len(text) > max_length:
        text = text[:max_length] + f"\n\n[... truncated at {max_length} characters]"
    #返回结果
    return text or "(empty response)"

def _edit_file(inp: dict) -> str:
    try:
            #根据文件读取内容content
        with open(inp["file_path"], encoding="utf-8") as f:
            content = f.read()
        #寻找old_string是否存在
        if inp["old_string"] not in content:
            #如果不存在返回错误，不匹配
            return f"Error: old_string not found in {inp['file_path']}"
        
        #如果存在，判断count是否大一1，如果大于1则返回错误
        count = content.count(inp["old_string"])
        if count > 1:
            return f"Error: old_string found {count} times in {inp['file_path']}. Must be unique."
        #存在且count等于1，则正确。把new_string替换到old_string
        new_content = content.replace(inp["old_string"],inp["new_string"])
        #把新的新的字符串写回到文件中
        with open(inp["file_path"], "w", encoding="utf-8") as f:
            f.write(new_content)
        #返回
        return  f"Successfully edited {inp['file_path']}"
    except Exception as e:
         return f"Error editing file: {e}"

def _write_file(inp: dict) -> str:
    try:
        path = Path(inp["file_path"])
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(inp["content"])
        lines = inp["content"]
        line_count = len(lines)
        preview = "\n".join(
        f"{i+1:4d} | {l}" for i,l in enumerate(lines[:30])
        )
        trunc = f"\n  ... ({line_count} lines total)" if line_count > 30 else ""
        return f"Successfully wrote to {inp['file_path']} ({line_count} lines)\n\n{preview}{trunc}"
    except Exception as e:
        return f"Error writing file: {e}"

def _list_files(inp: dict) -> str:
    d =Path(inp["file_path"])
    if not d.exists():
        return f"Error: directory not found: {d}"
    entries = sorted(d.iterdir(),key= lambda p: (p.is_file(),p.name))
    return "\n".join(
       f"{'[dir] ' if e.is_dir() else ''}{e.name}"
        for e in entries
    )


def _grep_search(inp: dict) -> str:
    try:
        # inp：{pattern, path(可选), include(可选：只搜某种文件，如 "*.py)}
        pattern = inp["pattern"]
        path = inp.get("path") or "."
        include = inp.get("include")
        # 拼命令
        args = ["grep","--line-number","--color=never","-r"]
        if include:
            args.append(f"--include={include}")
        args.extend(["--",pattern,path])
        # 调用subprocess执行命令
        result =subprocess.run(args,capture_output=True,timeout=10)
        #看returncode
        if result.returncode == 1:
            return "No matches found"
        if result.returncode != 0:
            return f"Error: {_decode_output(result.stderr)}"  # 退出码 2 = 真出错了
        #截断结果，截断到100行，主要为了防止上下文被撑爆
        stdout = _decode_output(result.stdout)
        lines = [l for l in stdout.split("\n") if l]
        output = "\n".join(lines[:100])
        if len(lines) > 100:
            output += f"\n... and {len(lines)-100} more matches"
        return output
    except Exception as e:
        return f"Error: {e}"

def _decode_output(data: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass  
    return data.decode("utf-8",errors="replace")



def _run_shell(inp:dict) -> str:
    try:
        timeout = inp.get("timeout", 30)
        result = subprocess.run(
            inp["command"],
            shell=True,
            capture_output=True,
            timeout=timeout
        )
        stdout = _decode_output(result.stdout)
        stderr = _decode_output(result.stderr)
        if result.returncode != 0:
            stderr = f"\nStderr: {stderr}"  if stderr else ""
            stdout = f"\nStdout: {stdout}" if stdout else ""
            return f"Command failed (exit code {result.returncode}){stdout}{stderr}"
        return stdout or "(no output)"    
    except subprocess.TimeoutExpired:
        return f"Command timed out after {inp.get('timeout', 30)}s"
    except Exception as e:
        return f"Error: {e}"



tool_handlers = {
    "read_file": _read_file,
    "edit_file": _edit_file,
    "write_file": _write_file,
    "list_files": _list_files,
    "grep_search": _grep_search,
    "run_shell": _run_shell,
    "get_weather": get_weather,
    "web_fetch": _web_fetch

}



def execute_tool(name: str, inp: dict) -> str:
    print(f"\n[TOOL CALLED] {name}")
    print(f"[TOOL INPUT] {inp}")

    try:
        
        function =  tool_handlers.get(name)
        if function is None:
            return f"错误：不存在工具：{name}"
        result = function(inp)
        return str(result)

    except Exception as e:
        return f"工具执行失败： {e}"





