from pathlib import Path
import json

SESSION_DIR = Path.home() / ".mini-agent" / "sessions"

def save_session(session_id: str, data: list[str,any]) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    (SESSION_DIR / f"{session_id}.json").write_text(
        json.dumps(data, indent=2, default=str)
    )
def ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

def list_sessions() -> list[dict[str, any]]:
    # 确保父目录存在
    ensure_dir()
    results = []
    #for遍历子目录的.json文件
    for f in SESSION_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if "metadata" in d:
                results.append(d["metadata"])
        except Exception:
            pass
    return results


def get_latest_session_id() -> str | None:
    #获取list_sessions
    sessions = list_sessions()
    if not sessions:
        return None
    #根据startTime排序
    sessions.sort(key = lambda s : s.get("startTime",""),reverse=True)
    #取出最近的id
    return sessions[0].get("id")
  #加载session  


def load_session(session_id: str) -> dict[str,any] | None:
    path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:    
        return json.loads(path.read_text())
    except Exception:
        return None 