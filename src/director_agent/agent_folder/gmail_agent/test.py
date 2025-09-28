
import os.path
import base64
from pathlib import Path  # <-- Make sure to import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

 # Renamed the function to be more accurate

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

def get_latest_gmail(query: str = "-category:{promotions social}") -> str:
    """Fetches the sender, subject, and body of the most recent email."""
    try:
        # 1. Get valid credentials first
        credentials = _get_gmail_credentials()
        
        # 2. Build the service object
        service = build('gmail', 'v1', credentials=credentials)

        # 3. API Call using the query parameter
        results = service.users().messages().list(
            userId='me', 
            maxResults=1, 
            q=query
        ).execute()
        
        messages = results.get('messages', [])

        if not messages:
            return f"No emails found matching the query: '{query}'"

        msg = service.users().messages().get(userId='me', id=messages[0]['id'], format='full').execute()

        # ... (rest of your parsing logic is correct)
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
        
        return f"From: {sender}\nSubject: {subject}\n\nBody:\n{body}"

    except Exception as e:
        return f"An error occurred while fetching emails: {e}"
# Add this block at the very end of your script
