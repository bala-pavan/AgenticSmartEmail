import os
import tempfile
import threading
import time
import logging
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
from google.oauth2 import service_account
from googleapiclient.discovery import build

# # Setup basic logging
# logging.basicConfig(filename='app.log', level=logging.INFO,
#                     format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__)

# Store the last processed email ID
last_processed_email_id = None

# Event to wake up the thread
email_event = threading.Event()

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


# Email fetching logic with rate limiting and retries

def get_latest_email(service):
    """
    Fetch the latest email, extract its details, and save attachments to a specified directory.
    """
    global last_processed_email_id

    try:
        save_dir = "attachments"
        # Fetch the latest email from the user's inbox
        results = service.users().messages().list(userId="me", maxResults=1, labelIds=["INBOX"]).execute()
        messages = results.get("messages", [])

        if not messages:
            logging.info("No new emails found.")
            return None, None

        latest_email = messages[0]

        # If the latest email is the same as the last processed one, skip processing
        if latest_email["id"] == last_processed_email_id:
            print("No new emails. Skipping.")
            return None, None

        # Get the message details
        message = service.users().messages().get(userId="me", id=latest_email["id"], format="raw").execute()
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

        # Update last processed email ID
        last_processed_email_id = latest_email["id"]

        return email_details, body

    except Exception as e:
        logging.error(f"An error occurred while retrieving the email: {e}")
        return None, None

def send_email_reply(service, original_email, reply_body):
    """
    Send a reply to the original email with meeting details.
    """
    try:
        original_sender = parseaddr(original_email['From'])[0]
        original_subject = original_email['Sub']
        original_recipient = parseaddr(original_email['To'])[0]

        reply_subject = f"Re: {original_subject}"

        # ##Check intent and format reply accordingly
        # if intent in ["Schedule meeting", "Reschedule meeting", "Cancel meeting"]:
        #     with open('reply_template.txt', 'r') as file:
        #         template = file.read()
 
        #     formatted_reply_body = template.format(
        #         original_sender=original_sender,
        #         reply_body=reply_body,
        #         original_recipient=original_recipient
        #     )
            
        # elif intent == "Policy inquiry":
        #     with open('policy_reply.txt', 'r') as file:
        #         template = file.read()
   
        #     formatted_reply_body = template.format(
        #         original_sender=original_sender,
        #         reply_body=reply_body,
        #         original_recipient=original_recipient
        #     )
        #     # formatted_reply_body = reply_body  # Directly use the detailed policy reply
        # else:
        #     with open('other_reply.txt', 'r') as file:
        #         template = file.read()
   
        #     formatted_reply_body = template.format(
        #         original_sender=original_sender,
        #         reply_body=reply_body,
        #         original_recipient=original_recipient
        #     )
        
        with open('reply_template.txt', 'r') as file:
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

        logging.info(f"Reply sent to {original_sender}")
        return sent_message

    except Exception as e:
        logging.error(f"An error occurred while sending the reply: {e}")
        return None
    

# def apply_label_to_email(service, email_id, label_name):
#     """Apply a label to the email in Gmail."""
#     try:
#         # Get the label ID for the given label name
#         labels_response = service.users().labels().list(userId="me").execute()
#         label_id = None
#         for label in labels_response["labels"]:
#             if label["name"] == label_name:
#                 label_id = label["id"]
#                 break
        
#         if label_id is None:
#             raise ValueError(f"Label '{label_name}' not found.")

#         # Apply the label to the email
#         msg_labels = {'addLabelIds': [label_id], 'removeLabelIds': ['INBOX']}
#         service.users().messages().modify(userId="me", id=email_id, body=msg_labels).execute()
#         print(f"Email moved to label '{label_name}'")
        
#     except Exception as e:
#         print(f"An error occurred while applying label: {e}")

# def create_label(service, label_name):
#     """Create a new label in Gmail."""
#     try:
#         label_object = {
#             "labelListVisibility": "labelShow",
#             "messageListVisibility": "show",
#             "name": label_name
#         }
#         created_label = service.users().labels().create(userId="me", body=label_object).execute()
#         print(f"Label '{label_name}' created.")
#         return created_label
#     except Exception as e:
#         print(f"An error occurred while creating the label: {e}")


@app.route('/fetch_and_classify_email', methods=['GET'])
def fetch_and_classify_email():
    """Fetch emails in the background every minute."""
    service = authenticate_gmail_api()
    while True:
        try:
            
            # Event to wake up the thread
            email_event = threading.Event()
            logging.info("Thread activated: Checking for unread emails.")
            
            latest_email, email_body = get_latest_email(service)

            if latest_email:
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
                send_email_reply(service, latest_email, reply_body)

                logging.info(f"Processed email with intent: {intent}")
                
            # Reset event (go back to idle state)
            email_event.clear()
        
        except Exception as e:
            logging.error(f"Error in background email fetch: {e}")

        time.sleep(30)  # Wait 1 minute before checking again
        
def email_watcher():
    """
    Separate thread to watch for unread emails and wake up the processing thread.
    """
    service = authenticate_gmail_api()

    while True:
        latest_email, _ = get_latest_email(service)

        if latest_email:
            logging.info("New unread email detected, waking up processing thread.")
            email_event.set()  # Wake up processing thread

        time.sleep(30)  # Check for new emails every 30 seconds

# Start background threads
processing_thread = threading.Thread(target=fetch_and_classify_email, daemon=True)
# watcher_thread = threading.Thread(target=email_watcher, daemon=True)

processing_thread.start()
# watcher_thread.start()

# # Start background thread
# thread = threading.Thread(target=fetch_and_classify_email, daemon=True)
# thread.start()

# @app.route('/status', methods=['GET'])
# def status():
#     """Check if the API is running."""
#     return jsonify({"message": "Flask email fetcher is running!"})

# @app.route('/fetch_and_classify_email', methods=['GET'])
# def fetch_and_classify_email():
#     """Fetch the latest email, classify its intent, and send an automatic reply."""
#     try:
#         service = authenticate_gmail_api()
#         latest_email, email_body = get_latest_email(service)

#         if not latest_email:
#             return jsonify({"error": "No emails found or unable to retrieve email content."}), 404

#         intent = classify_email_intent(email_body)
        
#         meeting_response = {"output": "Intent not recognized."}
#         if intent == "Schedule meeting":
#             meeting_response = agent_schedule_executor.invoke({"email_text": email_body, "intent": intent})
#         elif intent == "Reschedule meeting":
#             meeting_response = agent_reschedule_executor.invoke({"email_text": email_body, "intent": intent})
#         elif intent == "Cancel meeting":
#             meeting_response = agent_cancel_executor.invoke({"email_text": email_body, "intent": intent})
#         elif intent == "Policy inquiry":
#             meeting_response = agent_policy_executor.invoke({"email_text": email_body, "intent": intent})
            
            
#         # # If no valid response or agent was not triggered, move email to the "Categories" label
#         # if meeting_response.get("output") == "Intent not recognized." or agent_not_triggered_condition:  # Replace with the condition where agent fails
#         #     apply_label_to_email(service, latest_email['id'], "Categories")
        

#         reply_body = meeting_response.get("output", "No meeting details available.")
#         send_email_reply(service, latest_email, reply_body)

#         for attachment in latest_email.get("Attachments", []):
#             file_path = attachment.get("file_path")
#             if file_path and os.path.exists(file_path):
#                 os.remove(file_path)

#         return jsonify({
#             "email_details": latest_email,
#             "intent": intent,
#             "meeting_details": meeting_response
#         })

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # service = authenticate_gmail_api()
    #create_label(service, "Categories")
    app.run(debug=True, use_reloader=False)


