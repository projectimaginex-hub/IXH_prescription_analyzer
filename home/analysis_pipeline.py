from django.db import transaction
from .models import Prescription, Medicine, Symptom, LLMAudit
from .llm_utils import extract_symptoms_from_text, predict_medicines_from_symptoms, match_medicines_to_db

@transaction.atomic
def run_llm_analysis(prescription: Prescription):
    if not prescription.transcribed_text:
        raise ValueError("Prescription has no transcribed text to analyze.")

    # Step 1 — Extract Symptoms
    symptom_data = extract_symptoms_from_text(prescription.transcribed_text)
    LLMAudit.objects.create(
        prescription=prescription,
        model_name="symptom_extraction",
        prompt=prescription.transcribed_text,
        response=str(symptom_data)
    )

    for s in symptom_data.get("symptoms", []):
        obj, _ = Symptom.objects.get_or_create(name=s["name"].capitalize())
        prescription.symptoms.add(obj)

    # Step 2 — Predict Medicines
    patient = prescription.patient
    patient_info = {
        "age": patient.age,
        "gender": patient.gender,
        "weight": str(patient.weight),
    }
    med_suggestions = predict_medicines_from_symptoms(symptom_data, patient_info)
    LLMAudit.objects.create(
        prescription=prescription,
        model_name="medicine_prediction",
        prompt=str(symptom_data),
        response=str(med_suggestions)
    )

    # Step 3 — Map to DB
    db_meds = list(Medicine.objects.values_list("name", flat=True))
    matches = match_medicines_to_db([m["name"] for m in med_suggestions], db_meds)
    for suggested, matched in matches:
        if matched:
            med = Medicine.objects.get(name=matched)
            prescription.medicines.add(med)

    prescription.analysis_raw = {"symptoms": symptom_data, "medicines": med_suggestions}
    prescription.llm_analyzed = True
    prescription.save()
    return symptom_data, med_suggestions
