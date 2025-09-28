from __future__ import annotations
from typing import Any, Dict

from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a import A2AServer

def calendar_summary_tool(window: Dict[str, str] = None, tz: str = "America/New_York", traceId: str = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "data": {
            "events": [
                {"title": "Study Session", "start": "2025-09-28T10:00:00-04:00", "end":"2025-09-28T12:00:00-04:00", "location":"FIU Library"},
                {"title": "Trombone Practice", "start": "2025-09-29T09:30:00-04:00", "end":"2025-09-29T10:15:00-04:00", "location":"Music Hall 2"}
            ]
        },
        "summary": "2 upcoming events in your calendar.",
        "sms": "Calendar: 2 upcoming events.",
        "error": None,
        "traceId": traceId,
    }

CalendarTool = FunctionTool.from_fn(
    fn=calendar_summary_tool,
    name="calendar_summary",
    description="Return a summary of upcoming events (mock).",
)

calendar_agent = LlmAgent(
    name="calendar_agent",
    description="Calendar agent (A2A): returns upcoming events (mock demo).",
    tools=[CalendarTool],
    instruction="Always call tool `calendar_summary` with given window/tz/traceId and return only its JSON.",
)

def serve(host: str = "127.0.0.1", port: int = 7002):
    server = A2AServer(host=host, port=port, agents=[calendar_agent])
    print(f"[calendar_agent] A2A server on {host}:{port}")
    server.run()

if __name__ == "__main__":
    serve()
