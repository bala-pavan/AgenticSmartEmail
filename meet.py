import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain.agents import tool, AgentExecutor
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from auth import authenticate_google_calendar  # Assuming this is defined in `auth.py`
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages


from prompt import schedule_prompt, reschedule_prompt, cancel_prompt


# Load environment variables from .env
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
azure_endpoint = os.getenv("AZURE_ENDPOINT")

# Initialize Azure OpenAI model
llm = AzureChatOpenAI(
    deployment_name="gpt-4o",
    model_name="gpt-4o",
    temperature=0,
    openai_api_key=openai_api_key,
    azure_endpoint=azure_endpoint,
    openai_api_type="azure",
)

@tool
def schedule_meeting(email_text: str) -> str:
    """Schedules a meeting based on the email content, extracting details directly using the LLM."""
    try:
        # Create a prompt to extract details from the email
        meeting_prompt = f"""
        Please extract the following details from the following email text:
        Date
        Time (Convert in this format '%Y-%m-%d %I:%M %p %Z')
        Participants (Comma-separated emails)
        Summary
        Description
        
        Email text:
        {email_text}
        """

        # Use the model to extract the meeting details directly
        meeting_details_response = llm.invoke(meeting_prompt).content.strip()

        # Check if we received a valid response
        if not meeting_details_response:
            return "Could not extract meeting details from the email."

        # Parse the details from the LLM response (it might contain a list of details)
        meeting_details = {}

        # Split the response into key-value pairs based on labels
        details_lines = meeting_details_response.split("\n")

        # Now, process each line carefully
        for line in details_lines:
            line = line.strip()
            if line.startswith("Date:"):
                meeting_details["Date"] = line.split("Date:")[1].strip() if "Date:" in line else ""
            elif line.startswith("Time:"):
                meeting_details["Time"] = line.split("Time:")[1].strip() if "Time:" in line else ""
            elif line.startswith("Participants:"):
                meeting_details["Participants"] = line.split("Participants:")[1].strip() if "Participants:" in line else ""
            elif line.startswith("Summary:"):
                meeting_details["Summary"] = line.split("Summary:")[1].strip() if "Summary:" in line else ""
            elif line.startswith("Description:"):
                meeting_details["Description"] = line.split("Description:")[1].strip() if "Description:" in line else ""

        # Check if all necessary details are extracted
        if not all(key in meeting_details for key in ["Date", "Time", "Participants"]):
            return "Missing required meeting details (Date, Time, Participants)."

        # Ensure we are working with valid and non-empty data
        date_str = meeting_details["Date"]
        time_str = meeting_details["Time"]
        participants_str = meeting_details["Participants"]
        summary_str = meeting_details.get("Summary", "No summary provided")
        description_str = meeting_details.get("Description", "No description provided")

        # Check for extra date information and ensure the time is formatted correctly
        if date_str in time_str:
            time_str = time_str.replace(date_str, "").strip()  # Remove extra date from time string

        
        # Check if the date is in the past
        try:
            start_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p %Z")
        except ValueError as e:
            return f"Error parsing date or time: {str(e)}"
        
        # if start_time < datetime.utcnow():
        #     return "The date and time provided are in the past. Please provide a future date and time."


        duration = timedelta(hours=1)
        start_time_utc = start_time.isoformat() + 'Z'
        end_time_utc = (start_time + duration).isoformat() + 'Z'

        # Authenticate and initialize Google Calendar service
        calendar_service = authenticate_google_calendar()

        # Define event details
        event = {
            'summary': summary_str,
            'description': description_str,
            'start': {
                'dateTime': start_time_utc,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time_utc,
                'timeZone': 'UTC',
            },
            'attendees': [{'email': attendee.strip()} for attendee in participants_str.split(",")],
        }

        # Schedule the event in Google Calendar
        event = calendar_service.events().insert(calendarId='primary', body=event).execute()

        event_id = event.get('id')
        meeting_link = event.get('htmlLink')
        attendees_emails = ', '.join([attendee['email'] for attendee in event['attendees']])
        return f"Meeting scheduled successfully for {start_time_utc}. Attendees: {attendees_emails}. View event details: {meeting_link}. Event ID: {event_id}"

    except Exception as e:
        return f"Error scheduling meeting: {str(e)}"
@tool
def reschedule_meeting(email_text: str) -> str:
    """Reschedules a meeting based on the email content, extracting details directly using the LLM."""
    try:
        # Create a prompt to extract the details of the rescheduled meeting
        reschedule_prompt = f"""
        Please extract the following details from the following email text:
        Date
        Time (Convert in this format '%Y-%m-%d %I:%M %p %Z')
        Participants (Comma-separated emails)
        Summary
        Description
        
        Email text:
        {email_text}
        """

        # Use the model to extract the meeting details for rescheduling
        reschedule_details_response = llm.invoke(reschedule_prompt).content.strip()

        # Debug: print the response to see what the model returns
        print("Model response:", reschedule_details_response)

        # Check if we received a valid response
        if not reschedule_details_response:
            return "Could not extract rescheduling details from the email."

        # Parse the details from the LLM response
        reschedule_details = {}

        # Split the response into key-value pairs based on labels
        details_lines = reschedule_details_response.split("\n")

        for line in details_lines:
            line = line.strip()
            if line.startswith("Date:"):
                reschedule_details["Date"] = line.split("Date:")[1].strip() if "Date:" in line else ""
            elif line.startswith("Time:"):
                reschedule_details["Time"] = line.split("Time:")[1].strip() if "Time:" in line else ""
            elif line.startswith("Participants:"):
                reschedule_details["Participants"] = line.split("Participants:")[1].strip() if "Participants:" in line else ""
            elif line.startswith("Summary:"):
                reschedule_details["Summary"] = line.split("Summary:")[1].strip() if "Summary:" in line else ""
            elif line.startswith("Description:"):
                reschedule_details["Description"] = line.split("Description:")[1].strip() if "Description:" in line else ""

        # Check if all necessary details are extracted
        if not all(key in reschedule_details for key in ["Date", "Time", "Participants"]):
            return "Missing required rescheduling details (Date, Time, Participants)."

        # Extract and format the date and time
        new_date_str = reschedule_details["Date"]
        new_time_str = reschedule_details["Time"]
        participants_str = reschedule_details["Participants"]
        summary_str = reschedule_details.get("Summary", "No summary provided")
        description_str = reschedule_details.get("Description", "No description provided")

        if new_date_str in new_time_str:
            new_time_str = new_time_str.replace(new_date_str, "").strip()

        # Convert to datetime object for rescheduling
        try:
            new_start_time = datetime.strptime(f"{new_date_str} {new_time_str}", "%Y-%m-%d %I:%M %p %Z")
        except ValueError as e:
            return f"Error parsing new date or time: {str(e)}"

        new_duration = timedelta(hours=1)
        new_start_time_utc = new_start_time.isoformat() + 'Z'
        new_end_time_utc = (new_start_time + new_duration).isoformat() + 'Z'

        # Authenticate and initialize Google Calendar service
        calendar_service = authenticate_google_calendar()

        # Search for the event using the summary (or any other parameter that fits your case)
        events_result = calendar_service.events().list(
            calendarId='primary',
            q=summary_str,  # Search by the event summary (or remove this if you want to find any event)
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return f"No matching event found to reschedule for summary: {summary_str}. Please verify the event details."

        # Assuming the first event is the one to reschedule
        existing_event = events[0]
        event_id = existing_event['id']

        # Update the event with the new details
        existing_event['summary'] = summary_str
        existing_event['description'] = description_str
        existing_event['start'] = {
            'dateTime': new_start_time_utc,
            'timeZone': 'UTC',
        }
        existing_event['end'] = {
            'dateTime': new_end_time_utc,
            'timeZone': 'UTC',
        }
        existing_event['attendees'] = [{'email': attendee.strip()} for attendee in participants_str.split(",")]
        
        # Update the event in Google Calendar
        updated_event = calendar_service.events().update(calendarId='primary', eventId=event_id, body=existing_event).execute()

        meeting_link = updated_event.get('htmlLink')
        attendees_emails = ', '.join([attendee['email'] for attendee in updated_event['attendees']])
        return f"Meeting rescheduled successfully for {new_start_time_utc}. Attendees: {attendees_emails}. View updated event details: {meeting_link}. Event ID: {event_id}"

    except Exception as e:
        return f"Error rescheduling meeting: {str(e)}"
    

    
@tool
def cancel_meeting(email_text: str) -> str:
    """Cancels a meeting based on the email content, extracting details directly using the LLM."""
    try:
        # Create a prompt to extract the cancellation details
        cancel_prompt = f"""
        Please extract the following details from the following email text:
        Meeting Summary
        Meeting Date
        
        Email text:
        {email_text}
        """

        # Use the model to extract the cancellation details
        cancel_details_response = llm.invoke(cancel_prompt).content.strip()

        # Check if we received a valid response
        if not cancel_details_response:
            return "Could not extract cancellation details from the email."

        # Parse the cancellation details
        cancel_details = {}

        details_lines = cancel_details_response.split("\n")

        for line in details_lines:
            line = line.strip()
            if line.startswith("Meeting Summary:"):
                cancel_details["Meeting Summary"] = line.split("Meeting Summary:")[1].strip() if "Meeting Summary:" in line else ""
            elif line.startswith("Meeting Date:"):
                cancel_details["Meeting Date"] = line.split("Meeting Date:")[1].strip() if "Meeting Date:" in line else ""

        # Check if all necessary details are extracted
        if not all(key in cancel_details for key in ["Meeting Summary", "Meeting Date"]):
            return "Missing required cancellation details (Meeting Summary, Meeting Date)."

        # Extract the meeting details for cancellation
        meeting_summary = cancel_details["Meeting Summary"]
        meeting_date = cancel_details["Meeting Date"]

        # Authenticate and initialize Google Calendar service
        calendar_service = authenticate_google_calendar()

        # Find the event to cancel
        events_result = calendar_service.events().list(calendarId='primary', q=meeting_summary).execute()
        event = events_result.get('items', [])[0]  # Assuming the first event is the correct one

        # Delete the event from Google Calendar
        calendar_service.events().delete(calendarId='primary', eventId=event['id']).execute()
        event_id = event.get('id')

        return f"Meeting with summary '{meeting_summary}' on {meeting_date} has been canceled successfully."

    except Exception as e:
        return f"Error canceling meeting: {str(e)}"

llm_with_tools = llm.bind_tools([schedule_meeting,reschedule_meeting,cancel_meeting])

schedule_prompt_template = ChatPromptTemplate.from_messages([
    ("system", schedule_prompt),
    ("user", "{email_text}\nIntent: {intent}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

reschedule_prompt_template = ChatPromptTemplate.from_messages([
    ("system", reschedule_prompt),
    ("user", "{email_text}\nIntent: {intent}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

cancel_prompt_template = ChatPromptTemplate.from_messages([
    ("system", cancel_prompt),
    ("user", "{email_text}\nIntent: {intent}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])


schedule_agent = (
    {
        "email_text": lambda x: x["email_text"],
        "intent": lambda x: x["intent"],
        "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
    }
    | schedule_prompt_template
    | llm_with_tools
    | OpenAIToolsAgentOutputParser()
)

reschedule_agent = (
    {
        "email_text": lambda x: x["email_text"],
        "intent": lambda x: x["intent"],
        "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
    }
    | reschedule_prompt_template
    | llm_with_tools
    | OpenAIToolsAgentOutputParser()
)

cancel_agent = (
    {
        "email_text": lambda x: x["email_text"],
        "intent": lambda x: x["intent"],
        "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
    }
    | cancel_prompt_template
    | llm_with_tools
    | OpenAIToolsAgentOutputParser()
)

# Define agent executors
agent_schedule_executor = AgentExecutor(agent=schedule_agent, tools=[schedule_meeting, reschedule_meeting, cancel_meeting], verbose=True)
agent_reschedule_executor = AgentExecutor(agent=reschedule_agent, tools=[reschedule_meeting], verbose=True)
agent_cancel_executor = AgentExecutor(agent=cancel_agent, tools=[cancel_meeting], verbose=True)
