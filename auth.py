from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import pickle
import base64
from email import message_from_bytes
from email.header import decode_header
from googleapiclient.errors import HttpError


# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly','https://www.googleapis.com/auth/calendar.events','https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.modify','https://www.googleapis.com/auth/gmail.labels']

def authenticate_gmail_api():
    """Authenticate and return the Gmail API service."""
    creds = None
    # Load credentials if they exist
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If no valid credentials, prompt the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for future use
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    # Build and return the Gmail API service
    return build('gmail', 'v1', credentials=creds)

def get_latest_email(service):
    """Fetch the latest received email and format it in a readable structure."""
    try:
        # Fetch the latest message from the inbox
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return None

        # Fetch the full details of the latest message
        latest_message_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=latest_message_id, format='raw').execute()

        # Decode the raw email content
        raw_email = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
        email_message = message_from_bytes(raw_email)

        # Extract headers and body content
        email_details = {}

        # Sender details
        email_details['from'] = email_message['From']
        
        # Subject
        subject, encoding = decode_header(email_message['Subject'])[0]
        if isinstance(subject, bytes):
            email_details['subject'] = subject.decode(encoding or 'utf-8')
        else:
            email_details['subject'] = subject

        # To recipients
        email_details['to'] = email_message['To']

        # CC recipients, if any
        email_details['cc'] = email_message.get('Cc', 'None')

        # Email body (text or HTML)
        email_body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    email_body = part.get_payload(decode=True).decode("utf-8")
                    break
                elif content_type == "text/html" and "attachment" not in content_disposition:
                    email_body = part.get_payload(decode=True).decode("utf-8")
        else:
            email_body = email_message.get_payload(decode=True).decode("utf-8")

        email_details['body'] = email_body.strip()

        # Formatting email content in a structured Gmail-like format
        full_email_content = (
            f"From: {email_details['from']}\n"
            f"To: {email_details['to']}\n"
            f"CC: {email_details['cc']}\n"
            f"Subject: {email_details['subject']}\n\n"
            f"{email_details['body']}\n\n"
        )

        return {
            'content': full_email_content
        }
    except Exception as e:
        print(f"Error fetching the latest email: {e}")
        return None


def authenticate_google_calendar():
    """Authenticates the user with Google Calendar and returns a service object."""
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
    return build('calendar', 'v3', credentials=creds)

def create_message(sender, to, subject, body):
    """Create a message to send via Gmail API"""
    message = {
        'raw': base64.urlsafe_b64encode(
            f"From: {sender}\nTo: {to}\nSubject: {subject}\n\n{body}".encode("utf-8")
        ).decode("utf-8")
    }
    return message

def send_email(sender, recipient, subject, body):
    """Send an email using the Gmail API"""
    try:
        service = authenticate_gmail_api()
        message = create_message(sender, recipient, subject, body)
        send_message = service.users().messages().send(userId="me", body=message).execute()
        print(f"Message sent to {recipient}, Message ID: {send_message['id']}")
        return send_message
    except HttpError as error:
        print(f"An error occurred while sending email: {error}")
        return None

# After rescheduling, scheduling, or canceling the meeting, you can call this function
def send_confirmation_email(meeting_details, response):
    """Send a confirmation email after meeting action is completed."""
    sender_email = meeting_details["email_details"]["From"]  # Extract sender's email
    subject = f"Meeting Update: {response['intent']}"
    body = f"""
    Hello,

    The following meeting details have been processed:

    Intent: {response['intent']}
    Meeting Details: {response['meeting_details']['output']}

    Thank you!
    """
    send_email(sender_email, sender_email, subject, body)