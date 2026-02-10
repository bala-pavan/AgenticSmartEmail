
def generate_prompt(email_body):
    prompt = f"""
    You are a helpful assistant. Classify the intent of the following emails based on their content. The possible intents are:
    - "Schedule meeting"
    - "Reschedule meeting"
    - "Cancel meeting"
    - "Policy inquiry"
    - "Other"

    **Important instructions**:
    -Act case-insensitive.
    - Handle minor typos and spelling mistakes: "reschdule" should be treated as "reschedule", "timings" as "timing", and "call off" as "call meeting off".
    - Treat "Change"&"change","Call"&"call" as the same (case-insensitive). Variations like "change meeting", "change timings", "timings", and "timing" should be associated with "Reschedule meeting".
    - If the email contains any of the following phrases, classify it as "Reschedule meeting":
      - "reschdule", "change meeting", "postpone", "change timings", "timing", "schedule change", etc.
    - If the email contains "cancel", "call off", "call meeting off", classify it as "Cancel meeting".
    - If the email contains "schedule" or "set up" related to meetings, classify it as "Schedule meeting".
    - If the email does not match any of these, classify it as "Other".

    Here are some examples:

    1. "Let's schedule the meeting for tomorrow." → "Schedule meeting"
    2. "I need to reschedule our meeting." → "Reschedule meeting"
    3. "Can we postpone the meeting?" → "Reschedule meeting"
    4. "Please cancel the meeting tomorrow." → "Cancel meeting"
    5. "Change the timings of the meeting to today." → "Reschedule meeting"
    6. "I need to call off the meeting." → "Cancel meeting"
    7. "I want to set up a meeting with you." → "Schedule meeting"
    8. "Please confirm the time for the meeting." → "Other"

    Classify the following email:

    Email Body: {email_body}

    Intent:
    """
    return prompt

intent_prompt_template = """
You are a helpful assistant. Classify the intent of emails...
"""

schedule_prompt = """You are tasked with scheduling a meeting based on the following email details.\n\nEmail: {email_text}\nIntent: {intent}\nMeeting Details: """
reschedule_prompt = """You are tasked with rescheduling a meeting based on the following email details.\n\nEmail: {email_text}\nIntent: {intent}\nMeeting Details: """
cancel_prompt = """You are tasked with cancel a meeting based on the following email details.\n\nEmail: {email_text}\nIntent: {intent}\nMeeting Details: """