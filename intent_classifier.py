
import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from prompt import generate_prompt
 
# Load environment variables from .env
load_dotenv()
 
# Initialize the Azure OpenAI model
llm = AzureChatOpenAI(
    deployment_name="gpt-4-1106",
    model_name="gpt-4",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_ENDPOINT"),
    openai_api_type="azure",
)
 
def generate_prompt(email_body):
    return f"""
    The following email needs to be classified based on its intent. The possible intents are:
    1. Policy inquiry - Questions about insurance policies or plans, and specific document related queries
    2. Reschedule meeting - Requests to change the timing of an existing meeting.
    3. Cancel meeting - Requests to cancel a scheduled meeting.
    4. Schedule meeting - Requests to set up a new meeting.
    5. Other - If the email doesn't fall into any of the above categories.
   
    Examples:
    - "Explain the document below/attched document"-> Policy inquiry
    - "Can you tell me more about the Saral Jeevan Bima Yojana?" -> Policy inquiry
    - "Can we move our meeting to next Thursday?" -> Reschedule meeting
    - "I need to cancel our meeting tomorrow." -> Cancel meeting
    - "I'd like to set up a meeting next week to discuss our project." -> Schedule meeting
    - "I have a question about your services." -> Other
   
    Email content:
    {email_body}
   
    Please classify the intent of the email and respond with one of the intents above.
    """
 

def classify_email_intent(email_body):
    """
    Classify the intent of an email by using the LLM.
    """
    prompt = generate_prompt(email_body)
    try:
        response = llm.invoke([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ])
        intent = response.content.strip().lower()
        # Standardize LLM output
        intent_mapping = {
            "policy inquiry": "Policy inquiry",
            "reschedule meeting": "Reschedule meeting",
            "cancel meeting": "Cancel meeting",
            "schedule meeting": "Schedule meeting",
            "other": "Other",
        }
        return intent_mapping.get(intent, "Other")
    except Exception as e:
        print(f"Error in LLM classification: {e}")
        return "LLM Error"

