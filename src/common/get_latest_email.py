import os.path
import base64
from pathlib import Path  # <-- Make sure to import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# All the other necessary imports should be here too...

def _get_gmail_service():
    """Handles OAuth credentials and returns an authenticated Gmail API service object."""
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None

    # 1. Define the project root and file paths
    # Assuming your script is in .../src/agent_folder/gmail_agent/
    # we need to go up 3 levels to get to the project root.
    project_root = Path(__file__).resolve().parents[2]
    token_path = project_root / "src" / "common" / "token.json"
    credentials_path = project_root / "src" / "common" / "credentials.json"

    # 2. Check if a token already exists
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # 3. If no valid token, create or refresh one
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    # 4. Build and return the Gmail service object
    return build("gmail", "v1", credentials=creds)

_get_gmail_service()
