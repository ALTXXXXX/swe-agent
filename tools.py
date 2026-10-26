import json
from math import trunc
from pathlib import Path
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
}
    

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
    path = Path(inp["file_path"])
    if not path.exists():
        return f"Error: directory not found: {path}"
    entries = sorted(path.iterdir(),key= lambda p: (p.is_file(),p.name))
    return "\n".join(
       f"{'[dir]' if e.is_dir() else ''}{e.name}" for e in entries
    )



tool_handlers = {
    "read_file": _read_file,
    "edit_file": _edit_file,
    "write_file": _write_file,
    # "edit_file": _edit_file,
    "list_files": _list_files,
    # "grep_search": _grep_search,
    # "run_shell": _run_shell,
    "get_weather": get_weather

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





