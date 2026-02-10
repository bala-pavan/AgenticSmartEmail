from email import policy
from email.parser import BytesParser
from base64 import urlsafe_b64decode
import re

def get_original_email(service, reply_body):
    """Fetch the original email content from the conversation thread."""
    try:
        match = re.search(r'In-Reply-To: <(.+)>', reply_body)
        if match:
            original_message_id = match.group(1)
            original_message = service.users().messages().get(userId='me', id=original_message_id, format='raw').execute()
            msg_raw = urlsafe_b64decode(original_message['raw'].encode('ASCII'))
            msg = BytesParser(policy=policy.default).parsebytes(msg_raw)

            original_body = ""
            if msg.is_multipart():
                for part in msg.iter_parts():
                    if part.get_content_type() == "text/plain":
                        original_body = part.get_content().strip()
                        break
            else:
                original_body = msg.get_content().strip()

            return original_body
        else:
            return None
    except Exception as e:
        print(f"An error occurred while retrieving the original email: {e}")
        return None
