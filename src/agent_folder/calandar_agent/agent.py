# # calendar_agent.py
from google.adk.agents import Agent

import datetime as dt
import json
from pathlib import Path
import token
from typing import List, Dict, Any, Optional

# # (ADK imports are optional here; keeping them if you later wire tools)
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# # ---- Scopes (least privilege for reminders on a dedicated calendar)
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.app.created",
    "https://www.googleapis.com/auth/calendar.freebusy",
]

APP_CALENDAR_SUMMARY = "Reminders - ShellHacks"

# # ========= OAuth / Service =========
def _get_calendar_service():
    creds = None
    project_root = Path(__file__).resolve().parents[2]
    token_path = project_root / "token.json"
    
    if (project_root / "client_secret.json").exists():
        client_secret_path = project_root / "client_secret.json"
    elif (project_root / "contracts" / "client_secret.json").exists():
        client_secret_path = project_root / "contracts" / "client_secret.json"
    else:
        raise FileNotFoundError("client_secret.json not found in project root or contracts/")

    
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # <-- Make sure this file is in your project root

            
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

def _get_or_create_app_calendar(service, summary: str = APP_CALENDAR_SUMMARY) -> str:
    page_token = None
    while True:
        cl = service.calendarList().list(pageToken=page_token).execute()
        for item in cl.get("items", []):
            if item.get("summary") == summary:
                return item["id"]
        page_token = cl.get("nextPageToken")
        if not page_token:
            break
    created = service.calendars().insert(body={"summary": summary}).execute()
    return created["id"]

# # ========= Helper Tools (optional for ADK) =========
def list_reminders(time_min_iso: Optional[str] = None,
                   time_max_iso: Optional[str] = None,
                   max_results: int = 20) -> dict:
    service = _get_calendar_service()
    cal_id = _get_or_create_app_calendar(service)
    now = dt.datetime.utcnow().isoformat() + "Z"
    time_min = time_min_iso or now

    resp = service.events().list(
        calendarId=cal_id,
        timeMin=time_min,
        timeMax=time_max_iso,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return {"calendarId": cal_id, "reminders": resp.get("items", [])}

def add_reminder(title: str,
                 start_iso: str,
                 end_iso: Optional[str] = None,
                 timezone: str = "America/New_York",
                 minutes_before: int = 10) -> dict:
    """Creates a new calendar event/reminder in Google Calendar.

    This function adds an event to a dedicated application calendar. If the
    'end_iso' time is not provided, the event duration defaults to 30 minutes.
    The reminder is set as a popup notification before the start time.

    Args:
        title: The title or summary of the event/reminder.
        start_iso: The start time of the event in ISO 8601 format (e.g., "2025-10-27T10:00:00").
        end_iso: The optional end time of the event in ISO 8601 format. If None,
            the duration is set to 30 minutes.
        timezone: The timezone for the event. Defaults to "America/New_York".
            Use standard IANA timezone strings (e.g., "Europe/London").
        minutes_before: The number of minutes before the event start time to
            trigger a popup reminder. Defaults to 10 minutes.

    Returns:
        A dictionary containing the response from the Google Calendar API
        after successfully creating the event.

    Raises:
        googleapiclient.errors.Error: If the Google Calendar API call fails.
        ValueError: If ISO 8601 format for start_iso is invalid.
    """
    service = _get_calendar_service()
    cal_id = _get_or_create_app_calendar(service)

    if not end_iso:
        import datetime as dt # Imported here for the example, assume it's available
        start_dt = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_iso = (start_dt + dt.timedelta(minutes=30)).isoformat()

    body = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end":   {"dateTime": end_iso,   "timeZone": timezone},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": int(minutes_before)}]
        }
    }
    return service.events().insert(calendarId=cal_id, body=body).execute()

def freebusy(time_min_iso: str,
             time_max_iso: str,
             calendar_ids: Optional[List[str]] = None) -> dict:
    service = _get_calendar_service()
    items = [{"id": cid} for cid in (calendar_ids or ["primary"])]
    body = {"timeMin": time_min_iso, "timeMax": time_max_iso, "items": items}
    fb = service.freebusy().query(body=body).execute()
    return fb.get("calendars", {})

list_reminders = FunctionTool(func=list_reminders)
add_reminder  = FunctionTool(func=add_reminder)
freebusy       = FunctionTool(func=freebusy)

# # ========= Router Adapter =========
def handle_event_request_for_router(
    req: Dict[str, Any],
    *,
    use_app_calendar: bool = True,
    check_freebusy: bool = True,
    default_duration_min: int = 30
) -> Dict[str, Any]:
    trace_id = req.get("traceId")
    payload = req.get("payload", {})
    user = req.get("user", {})
    tz = user.get("tz") or "UTC"

    start_iso_in = (payload.get("start") or {}).get("dateTime")
    end_iso_in   = (payload.get("end")   or {}).get("dateTime")
    if not start_iso_in:
        return {"status": "error", "data": None, "error": "Missing start dateTime", "traceId": trace_id}

    if not end_iso_in:
        start_dt = dt.datetime.fromisoformat(start_iso_in.replace("Z", "+00:00"))
        end_iso_in = (start_dt + dt.timedelta(minutes=default_duration_min)).isoformat()

    overrides = []
    if isinstance(payload.get("reminders"), dict):
        minutes_before = payload["reminders"].get("minutesBefore", 10)
        overrides.append({"method": "popup", "minutes": int(minutes_before)})

    event_body = {
        "summary": payload.get("title", "(No title)"),
        "description": payload.get("notes"),
        "start": {"dateTime": start_iso_in, "timeZone": tz},
        "end":   {"dateTime": end_iso_in,   "timeZone": tz},
        "reminders": {"useDefault": False, "overrides": overrides} if overrides else {"useDefault": True},
    }

    service = _get_calendar_service()
    calendar_id = _get_or_create_app_calendar(service) if use_app_calendar else "primary"

    if check_freebusy:
        fb_body = {
            "timeMin": dt.datetime.fromisoformat(start_iso_in.replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": dt.datetime.fromisoformat(end_iso_in.replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "items": [{"id": "primary"}],
        }
        fb = service.freebusy().query(body=fb_body).execute()
        busy = fb.get("calendars", {}).get("primary", {}).get("busy", [])
        if busy:
            return {"status": "conflict", "data": None, "error": "Requested time is busy", "traceId": trace_id}

    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return {
        "status": "ok",
        "data": {
            "eventId": created.get("id"),
            "htmlLink": created.get("htmlLink"),
            "when": {"start": start_iso_in, "end": end_iso_in}
        },
        "error": None,
        "traceId": trace_id
    }

# # ========= Contract runner =========
def main_contract_flow():
    from pathlib import Path
    import json, sys

    # Resolve project root:  src/agents/calendar_agent.py -> project/
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[2]  # project root
    contracts_dir = project_root / "contracts"
    req_file = contracts_dir / "calendar.request.json"
    resp_file = contracts_dir / "calendar.response.json"

    print("[debug] script_path:", script_path)
    print("[debug] project_root:", project_root)
    print("[debug] req_file:", req_file)
    print("[debug] resp_file:", resp_file)

    if not req_file.exists():
        print(f"[error] Request file not found: {req_file}")
        print("Tip: create it here or update the code to point to the right path.")
        sys.exit(1)

    with open(req_file, "r") as f:
        req = json.load(f)

    resp = handle_event_request_for_router(req)

    # Ensure contracts dir exists
    contracts_dir.mkdir(parents=True, exist_ok=True)

    with open(resp_file, "w") as f:
        json.dump(resp, f, indent=2)

    print(f"[OK] wrote {resp_file}")
    print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    import argparse, asyncio, os, sys
    parser = argparse.ArgumentParser(description="Calendar agent runner")
    parser.add_argument("--mode", choices=["contracts", "adk"], default="contracts",
                        help="Run contracts JSON flow or ADK agent")
    parser.add_argument("--app-name", default="gcal_adk_app")
    parser.add_argument("--user-id", default="local_user")
    parser.add_argument("--session-id", default="demo")
    args = parser.parse_args()

    if args.mode == "contracts":
        # Your existing file-in/file-out flow
        main_contract_flow()
        sys.exit(0)

    # -------- ADK mode (LLM + tools) --------
    # Lazy-import ADK to avoid errors when not installed
    try:
        from google.adk.agents import Agent
        from google.adk.tools import FunctionTool
        from google.adk.sessions import InMemorySessionService
        from google.adk.runners import Runner
    except Exception as e:
        print("[error] ADK not available. `pip install google-adk`")
        raise

    # Ensure API key is present
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper() == "TRUE"
    if use_vertex:
        required = ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_APPLICATION_CREDENTIALS"]
        missing = [k for k in required if not os.getenv(k)]
        if missing:
            print("[error] Missing Vertex env vars:", ", ".join(missing))
            sys.exit(1)
    else:
        if not os.getenv("GOOGLE_GENAI_API_KEY"):
            print("[error] Missing GOOGLE_GENAI_API_KEY for AI Studio mode.")
            print("Either set an API key, or set GOOGLE_GENAI_USE_VERTEXAI=TRUE and Vertex envs.")
            sys.exit(1)

    # Wire tools using your existing functions
    list_reminders = FunctionTool(func=list_reminders)
    add_reminder = FunctionTool(func=add_reminder)
    freebusy = FunctionTool(func=freebusy)

root_agent = Agent(
    model="gemini-2.0-flash",
    name="calendar_agent",
    instruction=(
        "You are a scheduling assistant. Use `freebusy` to check availability, "
        "`add_reminder` to schedule, and `list_reminders` to show upcoming items. "
        "If `end_iso` is omitted, default to 30 minutes."
        "make sure to use eastern time and when creating events to only use september 28th 2025"
        ),
        tools=[ add_reminder,freebusy,list_reminders],
        )

async def run_adk():
    session_service = InMemorySessionService()
    await session_service.create_session(app_name=args.app_name, user_id=args.user_id, session_id=args.session_id)
    runner = Runner(agent=root_agent, app_name=args.app_name, session_service=session_service)

        # Sample prompts (edit/remove as needed)
    print(await runner.run(
        "Schedule a reminder 'Shellhacks Dinner' today at 5:30 PM (America/New_York), "
        "30 minutes long, popup 10 minutes before."
        ))
    print(await runner.run("Show my next 5 reminders on the app calendar."))
    print(await runner.run(
        "Am I busy tomorrow between 10am and 11am on my primary calendar?"
        ))
    asyncio.run(run_adk())

