from openai import OpenAI
import os
import json
import difflib
import logging
from dotenv import load_dotenv

# --- Google Gemini SDK Imports ---
from google import genai
from google.genai import types
from google.genai.errors import APIError as GeminiAPIError

# --- OpenAI SDK Imports ---
from openai import OpenAI
from openai import APIError as OpenAIAPIError 

logger = logging.getLogger(__name__)

# --- API KEY CONFIGURATION ---
load_dotenv()
# Your Gemini Key is used for medicine prediction
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
# Your OpenAI Key will be used for symptom prediction later
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") 


# --- LLM Client Initialization ---
# Initialize clients as None by default
gemini_client = None
openai_client = None

# 🧪 Initialize Gemini Client
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
else:
    logger.warning("GEMINI_API_KEY is missing. Medicine prediction will return dummy data.")

# 🧪 Initialize OpenAI Client (Will be None for now due to restriction)
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
else:
    logger.warning("OPENAI_API_KEY is missing. Symptom prediction will return dummy data.")


# --- PROMPT DEFINITIONS ---
SYMPTOM_PROMPT = """
You are a medical note analyzer. 
Input: a transcribed text generated from a patient's and doctor's audio note.
Return structured JSON ONLY. The JSON must contain the fields "symptoms" and "summary".
{{
  "symptoms": [{{"name": "<symptom>", "confidence": 0.0-1.0}}],
  "summary": "<1-line summary>"
}}
Text: {transcribed_text}
"""

MEDICINE_PROMPT = """
You are a clinical assistant suggesting potential medicines based on symptoms.
Input:
Symptoms: {symptoms_json}
Patient Info: {patient_info}

Output only a JSON array of medicine suggestions. The array must contain objects with the fields "name", "composition", and "reason".
[
  {
    "name": "<medicine name>", 
    ""composition"": "<e.g., Paracetamol 500mg>", 
    "reason": "<why suggested>", 
    "confidence": 0.0-1.0
  }
]
"""

# --- UTILITY FUNCTIONS ---

def _extract_json(text: str):
    """Safely extracts a JSON object or array from a string."""
    try:
        return json.loads(text)
    except Exception:
        # Tries to find and extract the outermost JSON structure ({} or [])
        start_curly = text.find('{')
        start_square = text.find('[')
        end_curly = text.rfind('}')
        end_square = text.rfind(']')

        if start_square != -1 and end_square != -1 and (start_curly == -1 or start_square < start_curly):
            # Treat as JSON array
            return json.loads(text[start_square:end_square+1])
        elif start_curly != -1 and end_curly != -1:
            # Treat as JSON object
            return json.loads(text[start_curly:end_curly+1])
            
        return {}


def call_llm(task_type: str, prompt_text: str):
    """
    Unified function to call the appropriate LLM (Gemini or OpenAI/GPT) 
    and handle dummy data fallback.
    """
    if task_type == 'symptom':
        # --- GPT-4 for Symptoms ---
        if openai_client:
            try:
                # Assuming your client is initialized to use GPT-4
                response = openai_client.chat.completions.create(
                    model="gpt-4",  # Using GPT-4 as requested
                    messages=[
                        {"role": "system", "content": "You extract symptoms as JSON only."},
                        {"role": "user", "content": prompt_text},
                    ],
                    temperature=0.0,
                    max_tokens=600,
                )
                return response.choices[0].message.content
            except OpenAIAPIError as e:
                logger.error(f"OpenAI API Error (Symptom): {e}. Returning dummy data.")
        
        # Dummy Fallback for Symptoms (Required when GPT-4 is restricted)
        return '{"symptoms": [{"name": "Dummy Cough", "confidence": 0.8}, {"name": "Dummy Fever", "confidence": 0.9}], "summary": "API restricted. Using dummy data."}'

    elif task_type == 'medicine':
        # --- Gemini for Medicine ---
        if gemini_client:
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "composition": {"type": "string"},
                                "reason": {"type": "string"},
                                "confidence": {"type": "number"}
                            }
                        }
                    }
                )
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash', # Using efficient model for structured output
                    contents=prompt_text,
                    config=config,
                )
                return response.text
            except GeminiAPIError as e:
                logger.error(f"Gemini API Error (Medicine): {e}. Returning dummy data.")
            except Exception as e:
                logger.error(f"Gemini processing error: {e}. Returning dummy data.")

        # Dummy Fallback for Medicines (Required when Gemini key is missing or API fails)
        return '[{"name": "Dummy Paracetamol", "composition": "500mg (Gemini Test)", "reason": "Placeholder reason for successful call.", "confidence": 0.99}, {"name": "Dummy Antacid", "composition": "250mg", "reason": "Placeholder reason for successful call.", "confidence": 0.7}]'

    return '{"error": "Invalid task type"}'


def extract_symptoms_from_text(transcribed_text: str):
    """Calls GPT-4 (or dummy) to extract symptoms."""
    prompt_text = SYMPTOM_PROMPT.format(transcribed_text=transcribed_text)
    raw = call_llm(task_type='symptom', prompt_text=prompt_text)
    return _extract_json(raw)


def predict_medicines_from_symptoms(symptoms_json, patient_info):
    """Calls Gemini (or dummy) to predict medicines."""
    prompt_text = MEDICINE_PROMPT.format(
        symptoms_json=json.dumps(symptoms_json), 
        patient_info=json.dumps(patient_info)
    )
    raw = call_llm(task_type='medicine', prompt_text=prompt_text)
    result = _extract_json(raw)
    
    # Ensure a list is returned
    return result if isinstance(result, list) else []


def match_medicines_to_db(suggested, db_meds):
    """Matches suggested medicine names to existing database entries."""
    matches = []
    # Assumes 'suggested' is a list of medicine names (strings)
    for name in suggested:
        close = difflib.get_close_matches(name, db_meds, n=1, cutoff=0.6)
        matches.append((name, close[0] if close else None))
    return matches