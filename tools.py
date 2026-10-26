import json
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



tool_handlers = {
    "read_file": _read_file,
    "edit_file": _edit_file,
    # "write_file": _write_file,
    # "edit_file": _edit_file,
    # "list_files": _list_files,
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

















