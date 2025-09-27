import os.path
import base64 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def _get_gmail_service():
    """Handles OAuth credentials and returns an authenticated Gmail API service object."""
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None
    
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)


def fetch_most_current_email():
    """
    Fetches the subject, sender, and body of the single most recent email 
    from the PRIMARY inbox.
    """
    try:
        service = _get_gmail_service()

        # 1. List messages, filtering for the PRIMARY category
        results = service.users().messages().list(
            userId='me', 
            maxResults=1, 
            labelIds=['CATEGORY_PERSONAL']  # <-- THIS IS THE NEW FILTER
        ).execute()
        
        messages = results.get('messages', [])

        if not messages:
            print("No new emails found in your Primary inbox.")
            return

        message_id = messages[0]['id']

        # 2. Get the full message content
        msg = service.users().messages().get(
            userId='me', 
            id=message_id, 
            format='full'
        ).execute()

        # 3. Extract Headers
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'NO SUBJECT')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'UNKNOWN SENDER')

        # 4. Extract and Decode the Plain Text Body
        payload = msg['payload']
        body = ""
        
        if 'parts' in payload:
            part = next((p for p in payload['parts'] if p['mimeType'] == 'text/plain'), None)
            if part:
                data = part['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
        else:
            data = payload['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8')

        print("--- Your Most Recent Primary Email ---")
        print(f"From: {sender}")
        print(f"Subject: {subject}")
        print("\n--- Body ---\n")
        print(body)

    except Exception as e:
        print(f"An error occurred: {e}")

# --- Run the function ---
if __name__ == '__main__':
    fetch_most_current_email()