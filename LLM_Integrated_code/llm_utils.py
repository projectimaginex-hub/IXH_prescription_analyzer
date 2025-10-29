import os
import json
import difflib
import logging

logger = logging.getLogger(__name__)

# --- LLM Connection (OpenAI Example) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    import openai
    openai.api_key = OPENAI_API_KEY
else:
    openai = None


SYMPTOM_PROMPT = """
You are a medical note analyzer. 
Input: a doctor's transcribed consultation note.
Return structured JSON:
{
  "symptoms": [{"name": "<symptom>", "confidence": 0.0-1.0}],
  "summary": "<1-line summary>"
}
"""

MEDICINE_PROMPT = """
You are a clinical assistant suggesting potential medicines based on symptoms.
Input:
Symptoms: {symptoms_json}
Patient Info: {patient_info}

Output only JSON array:
[
  {"name": "<medicine>", "reason": "<why>", "confidence": 0.0-1.0}
]
"""


def _extract_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            return {}
        try:
            return json.loads(text[start:end+1])
        except Exception:
            return {}


def call_openai(messages, model="gpt-4o-mini", max_tokens=600):
    if not openai:
        logger.warning("No OpenAI key found. Returning dummy response.")
        return '{"symptoms": [], "summary": ""}'
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return response["choices"][0]["message"]["content"]


def extract_symptoms_from_text(transcribed_text: str):
    messages = [
        {"role": "system", "content": "You extract symptoms as JSON only."},
        {"role": "user", "content": SYMPTOM_PROMPT.format(
            transcribed_text=transcribed_text)},
    ]
    raw = call_openai(messages)
    return _extract_json(raw)


def predict_medicines_from_symptoms(symptoms_json, patient_info):
    messages = [
        {"role": "system", "content": "You suggest possible medicines as JSON only."},
        {"role": "user", "content": MEDICINE_PROMPT.format(symptoms_json=json.dumps(
            symptoms_json), patient_info=json.dumps(patient_info))},
    ]
    raw = call_openai(messages)
    result = _extract_json(raw)
    return result if isinstance(result, list) else []


def match_medicines_to_db(suggested, db_meds):
    matches = []
    for name in suggested:
        close = difflib.get_close_matches(name, db_meds, n=1, cutoff=0.6)
        matches.append((name, close[0] if close else None))
    return matches
