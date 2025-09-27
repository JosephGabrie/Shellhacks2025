import os.path
import base64 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.adk.agents import Agent
from google_auth_oauthlib.flow import InstalledAppFlow


def get_latest_gmail(query: str = "-category:{promotions social}") -> str:
    """Fetches the sender, subject, and body of the most recent email in a user's Gmail inbox.

    Args:
        query: A valid Gmail search query to filter emails. 
               Defaults to '-category:{promotions social}' to search the Primary inbox.
               Example queries: 'from:billing@company.com', 'is:important'.

    Returns:
        A formatted string with the sender, subject, and body of the most recent email.
        Returns a 'not found' message if no emails match the query.
        Returns an error message if the API call fails.
    """
    try:
        # --- Authentication (remains the same) ---
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        service = build('gmail', 'v1', credentials=creds)

        # --- API Call using the query parameter ---
        results = service.users().messages().list(
            userId='me', 
            maxResults=1, 
            q=query  # Use the flexible query parameter
        ).execute()
        
        messages = results.get('messages', [])

        if not messages:
            return f"No emails found matching the query: '{query}'"

        msg = service.users().messages().get(userId='me', id=messages[0]['id'], format='full').execute()

        # --- Parsing (remains the same) ---
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'NO SUBJECT')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'UNKNOWN SENDER')
        
        body = ""
        if 'parts' in msg['payload']:
            part = next((p for p in msg['payload']['parts'] if p['mimeType'] == 'text/plain'), None)
            if part:
                data = part['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
        elif 'data' in msg['payload']['body']:
            data = msg['payload']['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        # --- Formatted Return for the agent ---
        return f"From: {sender}\nSubject: {subject}\n\nBody:\n{body}"

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