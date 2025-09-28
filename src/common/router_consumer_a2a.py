from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import json
import re
from datetime import datetime, timedelta, timezone

from google.adk.agents import LlmAgent
from google.adk.tools.transfer_to_agent_tool import TransferToAgentTool
from google.adk.a2a import AgentCard
from google.adk.runners import run_agent_once

# ---------- Agent cards (update host/port if needed) ----------
BANK_CARD  = AgentCard(name="banking_agent", host="127.0.0.1", port=7001)
CAL_CARD   = AgentCard(name="calendar_agent", host="127.0.0.1", port=7002)
GMAIL_CARD = AgentCard(name="gmail_agent",   host="127.0.0.1", port=7003)

# ---------- Keyword buckets for routing ----------
BANK_KWS  = ["bank", "balance", "spend", "spending", "merchant", "transaction", "subscriptions", "recurring", "charge", "debit", "credit", "rent", "cashflow"]
CAL_KWS   = ["calendar", "event", "schedule", "availability", "reminder", "meeting", "tomorrow", "today", "next week", "when am i free"]
GMAIL_KWS = ["gmail", "email", "inbox", "message", "tasks", "follow up", "subject", "from", "unread"]

DAILY_KWS = [
    "daily report", "today report", "todays report", "today's report",
    "daily summary", "today summary", "today's summary", "summary for today"
]

# ---------- Router agent ----------
router_agent = LlmAgent(
    name="router",
    description="Routes to Banking, Calendar, or Gmail agents over A2A. Can also aggregate a 'daily report' (all three). Answers general questions itself.",
    tools=[
        TransferToAgentTool.from_card(BANK_CARD,  name="to_banking"),
        TransferToAgentTool.from_card(CAL_CARD,   name="to_calendar"),
        TransferToAgentTool.from_card(GMAIL_CARD, name="to_gmail"),
    ],
    instruction=(
        "You are a router.\n"
        "If the user's query indicates a DAILY REPORT (keywords like: daily report, today's report, daily summary, today's summary), "
        "then CALL ALL THREE tools in this order: to_banking, to_calendar, to_gmail. "
        "Use the same payload object for all three tool calls (pass through window/json_path/tz/traceId/etc). "
        "Then construct and return ONE merged JSON:\n"
        "{\n"
        '  "status":"ok",\n'
        '  "data": { "banking": <JSON from banking tool>, "calendar": <JSON from calendar tool>, "gmail": <JSON from gmail tool> },\n'
        '  "summary": "Daily report for <YYYY-MM-DD>",\n'
        '  "error": null,\n'
        '  "traceId": payload.traceId\n'
        "}\n"
        "Otherwise, route as follows:\n"
        f"- Banking (keywords: {', '.join(BANK_KWS)}) -> call to_banking and return ONLY that tool's JSON.\n"
        f"- Calendar (keywords: {', '.join(CAL_KWS)}) -> call to_calendar and return ONLY that tool's JSON.\n"
        f"- Gmail (keywords: {', '.join(GMAIL_KWS)}) -> call to_gmail and return ONLY that tool's JSON.\n"
        "If none match, answer BRIEFLY yourself (no tools) with JSON like: "
        '{"status":"ok","data":{"answer":"..."},"error":null,"traceId":payload.traceId}.\n'
        "Be concise and always return valid JSON."
    ),
)

# ---------- Helper: default today's window in user's TZ (fallback to UTC) ----------
def _today_window(tz_str: Optional[str]) -> Dict[str, str]:
    # Simplified: assume local wall-clock 'today' without external tz lib; if tz_str present, we still compute naive today.
    today = datetime.now().date()
    since = datetime(today.year, today.month, today.day, 0, 0, 0).isoformat()
    until = datetime(today.year, today.month, today.day, 23, 59, 59).isoformat()
    return {"since": since, "until": until}

# ---------- Router wrapper class ----------
class RouterA2A:
    def __init__(self, agent: LlmAgent = router_agent):
        self.agent = agent

    def _ensure_daily_window(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # If no window provided, inject a "today" window so all three agents stay in sync.
        if not payload.get("window"):
            payload = dict(payload)  # shallow copy
            payload["window"] = _today_window(payload.get("tz") or payload.get("user", {}).get("tz"))
        return payload

    def route(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        task = envelope.get("task", "USER_QUERY")
        payload = envelope.get("payload", {}) or {}
        trace_id = envelope.get("traceId") or payload.get("traceId")

        query = (payload.get("query") or payload.get("prompt") or "").strip().lower()

        # DAILY REPORT fast-path: force multi-tool aggregation deterministically.
        if any(kw in query for kw in DAILY_KWS):
            payload = self._ensure_daily_window(payload)
            user_input = f"task={task}; payload={json.dumps(payload)}; query={query}; mode=daily"
            events = run_agent_once(self.agent, user_input=user_input)
            try:
                return json.loads(events[-1].content[0].text)
            except Exception:
                return {"status": "error", "error": "Router produced non-JSON response (daily report)", "traceId": trace_id}

        # Normal routing: let the router agent decide 1 target (bank/calendar/gmail) or self-answer
        user_input = f"task={task}; payload={json.dumps(payload)}; query={query}"
        events = run_agent_once(self.agent, user_input=user_input)
        try:
            return json.loads(events[-1].content[0].text)
        except Exception:
            return {"status": "error", "error": "Router produced non-JSON response", "traceId": trace_id}


if __name__ == "__main__":
    router = RouterA2A()

    # --- Example: DAILY REPORT (calls all three) ---
    daily_env = {
        "task": "USER_QUERY",
        "payload": {
            "query": "show me a daily report",
            "json_path": "/mnt/data/simulated_bank_data_single.json",
            "currency": "USD",
            "tz": "America/New_York",
            "traceId": "daily-001"
            # window omitted on purpose; router will inject today's window
        },
        "traceId": "daily-001"
    }
    import json as _json
    print("---- DAILY REPORT ----")
    print(_json.dumps(router.route(daily_env), indent=2))

    # --- Example: single target ---
    single_env = {
        "task": "USER_QUERY",
        "payload": {
            "query": "what events do i have today?",
            "tz": "America/New_York",
            "traceId": "cal-001"
        },
        "traceId": "cal-001"
    }
    print("---- CALENDAR ----")
    print(_json.dumps(router.route(single_env), indent=2))
