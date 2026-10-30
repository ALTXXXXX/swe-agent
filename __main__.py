import argparse
import os
import sys  
from agent import Agent
from session import load_session, save_session,list_sessions,get_latest_session_id
from dotenv import load_dotenv
load_dotenv()    
def parse_args()-> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mini-agent", add_help=False)
    parser.add_argument("prompt", nargs="*")
    parser.add_argument("--yolo", "-y", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--accept-edits", action="store_true")
    parser.add_argument("--dont-ask", action="store_true")
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument("--model", "-m", default=None)
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-cost", type=float, default=None)
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--help", "-h", action="store_true")
    return parser.parse_args()


def _resolve_permission_mode(args: argparse.Namespace) -> str:
    if args.yolo: return "bypassPermissions"
    if args.plan: return "plan"
    if args.accept_edits: return "acceptEdits"
    if args.dont_ask: return "dontAsk"
    return "default"


def main() -> None:
    args = parse_args()
    permission_mode = _resolve_permission_mode(args)
    model = args.model  or os.environ.get("Mini_AGENT_MODEL",'deepseek-flash')
    resolved_api_key: str | None = None
    provider: str | None = None
    env_base_url: str | None = None
    # 模型选择
    if os.environ.get("OPENAI_API_KEY"):
        provider = "openai"
        resolved_api_key = os.environ["OPENAI_API_KEY"]
        env_base_url = os.environ.get("OPENAI_BASE_URL")
    elif os.environ.get("ANTHROPIC_API_KEY"):
        provider = "anthropic"
        resolved_api_key = os.environ["ANTHROPIC_API_KEY"]
        env_base_url = os.environ.get("ANTHROPIC_BASE_URL")

    if not resolved_api_key:
        print("Error: API key is required.", file=sys.stderr)
        sys.exit(1)  

    if provider == "anthropic":
        print("Error: Anthropic provider is not implemented yet. Please use OPENAI_API_KEY for now.", file=sys.stderr)
        sys.exit(1)          
    api_base = args.api_base or env_base_url
    agent = Agent(
        provider = provider,
        permission_mode=permission_mode,
        model=model,
        thinking=args.thinking,
        max_cost_usd=args.max_cost,
        max_turns=args.max_turns,
        api_key=resolved_api_key,
        api_base=api_base)

    if args.resume:
        #获取session id
        #加载session
        print("resume进入")
        sid = get_latest_session_id()
        if sid:
            print("sid....")
            session = load_session(sid)
            if session:
                print("session加载")
                agent.restore_session(session)
                agent.replay_history()

    # 如果有prompt，则单次对话
    prompt = " ".join(args.prompt) if args.prompt else ""
    if prompt:
        agent.chat_once(prompt)
    else:
        agent.run()
        

    
    #否则run_REPL
if __name__ == "__main__":
    main()