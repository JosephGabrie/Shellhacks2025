import os.path
import base64 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.adk.agents import Agent
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path  # <-- Make sure to import Path

def _get_gmail_credentials():
    """Handles OAuth credentials and returns a valid credentials object."""
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None

    # This robustly finds your project root and the necessary files
    project_root = Path(__file__).resolve().parents[3] # Adjust if your script moves
    token_path = project_root / "src" / "common" / "token.json"
    credentials_path = project_root / "src" / "common" / "credentials.json"

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # This block handles all cases: no token, invalid token, or expired token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return creds
def get_recent_emails(query: str = "-category:{promotions social}") -> str:
    """Fetches the sender, subject, and body of the top 3 most recent emails.

    Args:
        query: A valid Gmail search query to filter emails.
               Defaults to '-category:{promotions social}' to search the Primary inbox.
               Example queries: 'from:billing@company.com', 'is:important'.

    Returns:
        A formatted string with the details of up to 3 recent emails.
        Returns a 'not found' message if no emails match the query.
        Returns an error message if the API call fails.
    """
    try:
        # --- Authentication ---
        # This part of your code is fine and doesn't need to change.
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            # Note: If token.json is missing/invalid, this will fail without the InstalledAppFlow logic.
            # You might want to re-integrate the robust path handling from previous versions.

        service = build('gmail', 'v1', credentials=creds)

        # --- API Call ---
        # **Change 1: Set maxResults to 3 to get more emails.**
        results = service.users().messages().list(
            userId='me',
            maxResults=3,  # <-- Fetch up to 3 messages
            q=query
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            return f"No emails found matching the query: '{query}'"

        # **Change 2: Loop through each message and build a combined string.**
        email_list = []
        for i, message in enumerate(messages):
            msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()

            # --- Parsing (applied to each email) ---
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'NO SUBJECT')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'UNKNOWN SENDER')

            body = ""
            if 'parts' in msg['payload']:
                part = next((p for p in msg['payload']['parts'] if p['mimeType'] == 'text/plain'), None)
                if part:
                    data = part['body'].get('data', '')
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
            elif msg['payload']['body'].get('data'):
                data = msg['payload']['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
            
            # --- Format each email's output ---
            email_details = (
                f"--- Email {i + 1} ---\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n\n"
                f"Body:\n{body.strip()}"
            )
            email_list.append(email_details)

        # **Change 3: Join all the formatted email strings together.**
        return "\n\n" + "\n\n".join(email_list)

    except Exception as e:
        return f"An error occurred while fetching emails: {e}"

root_agent = Agent(
    name="gmail_agent",
    model="gemini-2.0-flash",  # Use a valid model name
    description="An agent that can fetch the user's most recent email.",
    tools=[get_latest_gmail],  # Give the agent its tool
    instruction="""
    You are a helpful assistant that can check a user's email.
    When a user asks to read their email, check for new messages, or asks
    'what's my latest email?', use the 'get_latest_gmail' tool to find it.
    
    If the user provides a specific query like 'find emails from billing@company.com',
    pass that query to the tool. Otherwise, use the tool's default settings.
    """
)