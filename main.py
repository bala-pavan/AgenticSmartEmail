
import os
import tempfile
from base64 import urlsafe_b64decode, urlsafe_b64encode
from email import policy
from email.mime.text import MIMEText
from email.parser import BytesParser
from email.utils import parseaddr
from flask import Flask, jsonify
from auth import authenticate_gmail_api
from intent_classifier import classify_email_intent
from meet import agent_cancel_executor, agent_reschedule_executor, agent_schedule_executor
from policy import agent_policy_executor

app = Flask(__name__)

def extract_latest_email_content(email_body):
    """
    Extract only the latest email content from the thread.
    Remove follow-ups, timestamps, and reply/forward information.
    """
    lines = email_body.splitlines()
    latest_email_lines = []

    for line in lines:
        if line.strip().lower().startswith(("on ", "forwarded message", "wrote:")):
            break
        latest_email_lines.append(line)

    return "\n".join(latest_email_lines).strip()

def get_latest_email(service, save_dir="attachments"):
    """
    Fetch the latest email, extract its details, and save attachments to a specified directory.
    """
    try:
        # Fetch the latest email from the user's inbox
        results = service.users().messages().list(userId="me", maxResults=1, labelIds=["INBOX"]).execute()
        messages = results.get("messages", [])

        if not messages:
            print("No new emails found.")
            return None, None

        # Get the message details
        message = service.users().messages().get(userId="me", id=messages[0]["id"], format="raw").execute()
        msg_raw = urlsafe_b64decode(message["raw"].encode("ASCII"))
        msg = BytesParser(policy=policy.default).parsebytes(msg_raw)

        sender = msg.get("From", "Unknown sender")
        recipients = msg.get("To", "Unknown recipient")
        cc = msg.get("Cc", "None")
        subject = msg.get("Subject", "No subject")
        date = msg.get("Date", "Unknown date")
        body = ""
        attachments = []

        # Ensure the directory for saving attachments exists
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Process email body and attachments
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = part.get("Content-Disposition", "")
                content_type = part.get_content_type()

                if content_disposition and "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        file_path = os.path.join(save_dir, filename)
                        with open(file_path, "wb") as file:
                            file.write(part.get_payload(decode=True))
                        attachments.append({"filename": filename, "file_path": file_path})

                elif content_type == "text/plain" and not content_disposition:
                    body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8") + "\n"

                elif content_type == "text/html" and not body:
                    html_content = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
                    body += html_content + "\n"
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                body += msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
            elif content_type == "text/html":
                html_content = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
                body += html_content
            

        email_details = {
            "From": sender,
            "To": recipients,
            "CC": cc,
            "Sub": subject,
            "Email body": body,
            "Date": date,
            "Attachments": attachments,
        }
        
        # 1. read attachements in dict scenario a: 

        return email_details, body

    except Exception as e:
        print(f"An error occurred while retrieving the email: {e}")
        return None, None

def send_email_reply(service, original_email, reply_body, intent):
    """
    Send a reply to the original email with meeting details.
    """
    try:
        original_sender = parseaddr(original_email['From'])[0]
        original_subject = original_email['Sub']
        original_recipient = parseaddr(original_email['To'])[0]

        reply_subject = f"Re: {original_subject}"

        #Check intent and format reply accordingly
        if intent in ["Schedule meeting", "Reschedule meeting", "Cancel meeting"]:
            with open('meetings_reply.txt', 'r') as file:
                template = file.read()
 
            formatted_reply_body = template.format(
                original_sender=original_sender,
                reply_body=reply_body,
                original_recipient=original_recipient
            )
        elif intent == "Policy inquiry":
            with open('policy_reply.txt', 'r') as file:
                template = file.read()
    
            formatted_reply_body = template.format(
                original_sender=original_sender,
                reply_body=reply_body,
                original_recipient=original_recipient
            )
            # formatted_reply_body = reply_body  # Directly use the detailed policy reply
        else:
            with open('other_reply.txt', 'r') as file:
                template = file.read()
    
            formatted_reply_body = template.format(
                original_sender=original_sender,
                reply_body=reply_body,
                original_recipient=original_recipient
            )

        message = MIMEText(formatted_reply_body, "plain")
        message['To'] = original_email['From']
        message['Subject'] = reply_subject

        raw_message = urlsafe_b64encode(message.as_bytes()).decode()

        sent_message = service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()

        print(f"Reply sent to {original_sender}")
        return sent_message

    except Exception as e:
        print(f"An error occurred while sending the reply: {e}")
        return None

@app.route('/fetch_and_classify_email', methods=['GET'])
def fetch_and_classify_email():
    """Fetch the latest email, classify its intent, and send an automatic reply."""
    try:
        service = authenticate_gmail_api()
        latest_email, email_body = get_latest_email(service, save_dir="attachments")

        if not latest_email:
            return jsonify({"error": "No emails found or unable to retrieve email content."}), 404

        intent = classify_email_intent(email_body)

        meeting_response = {"output": "Intent not recognized."}
        if intent == "Schedule meeting":
            meeting_response = agent_schedule_executor.invoke({"email_text": email_body, "intent": intent})
        elif intent == "Reschedule meeting":
            meeting_response = agent_reschedule_executor.invoke({"email_text": email_body, "intent": intent})
        elif intent == "Cancel meeting":
            meeting_response = agent_cancel_executor.invoke({"email_text": email_body, "intent": intent})
        elif intent == "Policy inquiry":
            meeting_response = agent_policy_executor.invoke({"email_text": email_body, "intent": intent})

        reply_body = meeting_response.get("output", "No meeting details available.")
        send_email_reply(service, latest_email, reply_body,intent)

        for attachment in latest_email.get("Attachments", []):
            file_path = attachment.get("file_path")
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

        # Format the response based on intent
        if intent in ["Schedule meeting", "Reschedule meeting", "Cancel meeting"]:

            response = {
                "email_details": latest_email,
                "intent": intent,
                "meeting_details": meeting_response
            }
        elif intent == "Policy inquiry":  # Updated intent match
            response = {
                "email_details": latest_email,
                "intent": intent,
                "policy_details": meeting_response
            }
        else:
            response = {
                "email_details": "Unrecognized intent",
                "intent": intent,
                "details": "Unable to process the request."
            }

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True)



