from __future__ import annotations
from typing import Any, Dict

from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a import A2AServer

def gmail_tasks_tool(window: Dict[str, str] = None, from_filter: str = None, traceId: str = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "data": {
            "tasks": [
                {"subject":"Submit assignment 2", "due":"2025-09-30", "from":"Professor Baker"},
                {"subject":"Buy reeds", "due":"2025-10-01", "from":"Self"}
            ]
        },
        "summary": "2 tasks detected from inbox (mock).",
        "sms": "Gmail: 2 tasks.",
        "error": None,
        "traceId": traceId,
    }

GmailTool = FunctionTool.from_fn(
    fn=gmail_tasks_tool,
    name="gmail_tasks",
    description="Extract tasks from Gmail (mock).",
)

gmail_agent = LlmAgent(
    name="gmail_agent",
    description="Gmail agent (A2A): extracts tasks from emails (mock demo).",
    tools=[GmailTool],
    instruction="Always call tool `gmail_tasks` with given params and return only its JSON.",
)

def serve(host: str = "127.0.0.1", port: int = 7003):
    server = A2AServer(host=host, port=port, agents=[gmail_agent])
    print(f"[gmail_agent] A2A server on {host}:{port}")
    server.run()

if __name__ == "__main__":
    serve()
