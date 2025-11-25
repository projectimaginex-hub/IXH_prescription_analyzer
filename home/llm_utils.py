import os
import json
import difflib
import logging
from dotenv import load_dotenv
import PIL.Image  # <--- Essential for OCR

# --- Google Gemini SDK Imports ---
import google.generativeai as genai
from google.generativeai import types
from google.api_core.exceptions import GoogleAPIError as GeminiAPIError

# --- OpenAI SDK Imports ---
from openai import OpenAI
from openai import APIError as OpenAIAPIError

logger = logging.getLogger(__name__)

# --- API KEY CONFIGURATION ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- LLM Client Initialization ---
gemini_client = None
openai_client = None

if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")

if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")


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

PATIENT HISTORY (From scanned documents):
{history_text}

Output only a JSON array of medicine suggestions. The array must contain objects with the fields "name", "composition", and "reason".
[
  {
    "name": "<medicine name>", 
    "composition": "<e.g., Paracetamol 500mg>", 
    "reason": "<why suggested>", 
    "confidence": 0.0-1.0
  }
]
"""

OCR_PROMPT = """
You are an expert medical data transcriber. 
Analyze this image of a medical prescription or report.
Extract the following details into a strict JSON format:
{
  "patient_name": "Name or null",
  "age": "Age or null",
  "gender": "Male/Female/Other or null",
  "symptoms": ["symptom1", "symptom2"],
  "medicines": ["med1", "med2"],
  "summary": "A short summary of the document"
}
If the text is handwritten and hard to read, do your best to infer based on medical context.
Return ONLY the JSON.
"""

# --- UTILITY FUNCTIONS ---

def _extract_json(text: str):
    """Safely extracts a JSON object or array from a string."""
    try:
        return json.loads(text)
    except Exception:
        start_curly = text.find('{')
        start_square = text.find('[')
        end_curly = text.rfind('}')
        end_square = text.rfind(']')

        if start_square != -1 and end_square != -1 and (start_curly == -1 or start_square < start_curly):
            return json.loads(text[start_square:end_square+1])
        elif start_curly != -1 and end_curly != -1:
            return json.loads(text[start_curly:end_curly+1])
        return {}


def call_llm(task_type: str, prompt_text: str):
    """Unified function to call the appropriate LLM."""
    if task_type == 'symptom':
        if openai_client:
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You extract symptoms as JSON only."},
                        {"role": "user", "content": prompt_text},
                    ],
                    temperature=0.0,
                    max_tokens=600,
                )
                return response.choices[0].message.content
            except OpenAIAPIError as e:
                logger.error(f"OpenAI API Error: {e}")
        return '{"symptoms": [], "summary": "API restricted."}'

    elif task_type == 'medicine':
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
                    model='gemini-2.0-flash', 
                    contents=prompt_text,
                    config=config,
                )
                return response.text
            except Exception as e:
                logger.error(f"Gemini processing error: {e}")
        return '[]'

    return '{"error": "Invalid task type"}'


def extract_symptoms_from_text(transcribed_text: str):
    """Calls GPT-4 to extract symptoms."""
    prompt_text = SYMPTOM_PROMPT.format(transcribed_text=transcribed_text)
    raw = call_llm(task_type='symptom', prompt_text=prompt_text)
    return _extract_json(raw)


def predict_medicines_from_symptoms(symptoms_json, patient_info, include_history=False):
    """Calls Gemini to predict medicines, optionally using history."""
    
    # 1. Look up history if requested
    history_text = "No history found."
    if include_history:
        p_name = patient_info.get('name') or patient_info.get('patientName')
        if p_name:
            # Avoid circular import by importing inside function
            from .models import MedicalHistory, Patient
            patients = Patient.objects.filter(name__iexact=p_name)
            if patients.exists():
                p = patients.first()
                scans = MedicalHistory.objects.filter(patient=p).order_by('-date_scanned')[:3]
                if scans.exists():
                    history_list = [s.summary_text for s in scans]
                    history_text = "; ".join(history_list)

    # 2. Format Prompt
    prompt_text = MEDICINE_PROMPT.format(
        symptoms_json=json.dumps(symptoms_json),
        patient_info=json.dumps(patient_info),
        history_text=history_text
    )
    
    # 3. Call LLM
    raw = call_llm(task_type='medicine', prompt_text=prompt_text)
    result = _extract_json(raw)
    return result if isinstance(result, list) else []


# --- THE MISSING FUNCTION ---
def analyze_medical_document_image(image_file):
    """
    Accepts an uploaded image file, converts it for Gemini,
    and returns the extracted JSON data.
    """
    if not gemini_client:
        return {"error": "Gemini API key not configured."}

    try:
        # 1. Convert Django UploadedFile to PIL Image
        image = PIL.Image.open(image_file)
        
        # 2. Call Gemini (Multimodal)
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[OCR_PROMPT, image]
        )
        
        # 3. Clean and Parse JSON
        return _extract_json(response.text)

    except Exception as e:
        logger.error(f"OCR Analysis Failed: {e}")
        return {"error": str(e), "symptoms": [], "medicines": []}

def match_medicines_to_db(suggested, db_meds):
    """Matches suggested medicine names to existing database entries."""
    matches = []
    for name in suggested:
        close = difflib.get_close_matches(name, db_meds, n=1, cutoff=0.6)
        matches.append((name, close[0] if close else None))
    return matches