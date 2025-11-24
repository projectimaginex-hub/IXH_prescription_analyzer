import logging
import traceback
import io
import time
import requests
import json  # ADDED
from django.utils import timezone
from django.core.mail import EmailMessage
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404  # UPDATED
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from .forms import ContactForm
from reportlab.lib.units import inch
from .models import Patient, Prescription, Doctor
from .forms import UserForm, DoctorForm, DoctorProfileUpdateForm, ClinicInfoForm  # UPDATED
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Patient, Prescription, Doctor, Symptom, Medicine, Audio, ContactSubmission
from .llm_utils import extract_symptoms_from_text, predict_medicines_from_symptoms  # LLM imports
from django.db import transaction

# For drawing uploaded logo in PDF
from reportlab.lib.utils import ImageReader
from django.conf import settings
import os


from twilio.rest import Client

# --- ASSEMBLYAI API CONFIG ---
ASSEMBLYAI_UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
ASSEMBLYAI_TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'


logger = logging.getLogger(__name__)


# --- NEW VIEW: CLINIC CONFIGURATION (REINFORCED) ---
@login_required
def clinic_config_view(request):
    """
    Handles displaying and saving the Doctor's clinic name, address, and logo.
    Safely handles the case where a User is logged in but has no Doctor profile.
    """
    try:
        doctor_profile = request.user.doctor
    except Doctor.DoesNotExist:
        messages.error(
            request, "Please complete your main Doctor profile setup before configuring clinic settings.")
        return redirect('edit-profile')

    if request.method == 'POST':
        form = ClinicInfoForm(request.POST, request.FILES,
                              instance=doctor_profile)
        if form.is_valid():
            form.save()
            messages.success(
                request, 'Clinic details updated successfully! Your new logo will appear on prescriptions.')
            return redirect('clinic-config')
    else:
        form = ClinicInfoForm(instance=doctor_profile)

    return render(request, 'clinic_config.html', {'form': form, 'doctor_profile': doctor_profile})


# --- NEW VIEW FOR TRANSCRIPTION ---


@csrf_exempt
def transcribe_audio(request):
    if request.method == 'POST':
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return JsonResponse({'status': 'error', 'message': 'No audio file received.'}, status=400)
        headers = {'authorization': settings.ASSEMBLYAI_API_KEY}
        try:
            upload_response = requests.post(
                ASSEMBLYAI_UPLOAD_ENDPOINT, headers=headers, data=audio_file.read(), verify=False
            )
            upload_response.raise_for_status()
            upload_url = upload_response.json()['upload_url']
        except requests.RequestException as e:
            return JsonResponse({'status': 'error', 'message': f'Failed to upload audio: {e}'}, status=500)

        json_data = {'audio_url': upload_url}
        try:
            transcript_response = requests.post(
                ASSEMBLYAI_TRANSCRIPT_ENDPOINT, json=json_data, headers=headers, verify=False
            )
            transcript_response.raise_for_status()
            transcript_id = transcript_response.json()['id']
        except requests.RequestException as e:
            return JsonResponse({'status': 'error', 'message': f'Failed to request transcript: {e}'}, status=500)

        polling_endpoint = f"{ASSEMBLYAI_TRANSCRIPT_ENDPOINT}/{transcript_id}"
        for _ in range(20):
            try:
                polling_response = requests.get(
                    polling_endpoint, headers=headers, verify=False)
                polling_response.raise_for_status()
                polling_result = polling_response.json()
                if polling_result['status'] == 'completed':
                    return JsonResponse({'status': 'success', 'text': polling_result['text']})
                elif polling_result['status'] == 'error':
                    return JsonResponse({'status': 'error', 'message': polling_result['error']}, status=500)
                time.sleep(3)
            except requests.RequestException as e:
                return JsonResponse({'status': 'error', 'message': f'Polling failed: {e}'}, status=500)
        return JsonResponse({'status': 'error', 'message': 'Transcription timed out.'}, status=408)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


# --- NEW VIEW: AI Symptom Prediction Endpoint ---


@csrf_exempt
def get_ai_symptoms(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            transcribed_text = data.get('transcribed_text', '').strip()
            print(transcribed_text)
            if not transcribed_text:
                return JsonResponse({'status': 'error', 'message': 'Transcription text is required for analysis.'}, status=400)

            # --- CALL THE LLM UTILITY FUNCTION ---
            symptom_data = extract_symptoms_from_text(transcribed_text)

            # Extract names from the LLM's structured JSON response
            predicted_symptoms = [s['name'].capitalize()
                                  for s in symptom_data.get('symptoms', [])]

            return JsonResponse({'status': 'success', 'symptoms': predicted_symptoms})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            traceback.print_exc()  # 👈 This shows the real Python error
            return JsonResponse({'status': 'error', 'message': f'AI Prediction Error: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


# --- CORE PRESCRIPTION VIEW (FIXED PDF & DYNAMIC CLINIC DATA) ---

@login_required
def prescription(request):
    """
    Handles the 'Verify & Save' submission via an asynchronous request (AJAX).
    1. Saves Patient/Prescription/Symptoms/Medicines (FIXED: All data saved before PDF).
    2. Generates PDF using dynamic clinic branding (FIXED: Uses persistent data).
    """
    if request.method == 'POST':
        # --- 1. GATHER ALL DATA ---
        audio_file = request.FILES.get('audio')
        transcribed_text = request.POST.get('transcriptionText')
        email = request.POST.get('email')
        patient_name = request.POST.get('patientName')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('bloodGrp')
        weight = request.POST.get('weight')
        blood_pressure = request.POST.get('bp')
        address = request.POST.get('address')
        allergy = request.POST.get('allergy')

        confirmed_symptoms_str = request.POST.get('confirmedSymptoms', '')
        # FIX: Corrected variable name from confirmed_symptom_str to confirmed_symptoms_str
        confirmed_symptom_names = [
            s.strip() for s in confirmed_symptoms_str.split(',') if s.strip()]

        confirmed_medicines_str = request.POST.get('confirmedMedicines', '')
        # FIX: Corrected variable name from confirmed_medicine_str to confirmed_medicines_str
        confirmed_medicine_names = [
            m.strip() for m in confirmed_medicines_str.split(',') if m.strip()]

        age_val = int(age) if age and age.isdigit() else None
        weight_val = float(weight) if weight and weight.replace(
            '.', '', 1).isdigit() else None

        with transaction.atomic():
            # --- 2. CREATE/UPDATE PATIENT & DOCTOR CHECK ---
            patient, _ = Patient.objects.update_or_create(
                phone=phone, name=patient_name, defaults={
                    'age': age_val, 'email': email, 'gender': gender, 'blood_group': blood_group, 'weight': weight_val, 'address': address, 'allergy': allergy}
            )

            try:
                doctor = request.user.doctor
            except Doctor.DoesNotExist:
                doctor = None

            # --- Safely Define All Doctor/Clinic Variables (CRITICAL FIX) ---
            if doctor:
                doctor_full_name = f"MD. {
                    doctor.first_name} {doctor.last_name}"
                doctor_spec = doctor.specialization or "General Physician"
                # CRITICAL: If ID is null, use a large integer fallback
                clinic_id = str(doctor.id) if doctor.id else "123456789"
                clinic_name = doctor.clinic_name or "MEDICAL CLINIC NAME"
                clinic_address = doctor.clinic_address or "123, Lorem Ipsum St. | +00 123 456 789 | clinicname@email.com"

                # Check if logo exists and get the full path
                if doctor.clinic_logo and doctor.clinic_logo.name:
                    clinic_logo_path = os.path.join(
                        settings.MEDIA_ROOT, doctor.clinic_logo.name)
                else:
                    clinic_logo_path = None
            else:
                # Fallback values if no Doctor profile exists
                doctor_full_name = "MD. ABC DEF (Setup Profile)"
                doctor_spec = "General Physician"
                clinic_id = "123456789"
                clinic_name = "MEDICAL CLINIC NAME (Default)"
                clinic_address = "123, Lorem Ipsum St. | +00 123 456 789 | clinicname@email.com"
                clinic_logo_path = None

            new_prescription = Prescription.objects.create(
                patient=patient, doctor=doctor, blood_pressure=blood_pressure,
                transcribed_text=transcribed_text, is_verified=True, verified_at=timezone.now()
            )

            # --- 3. SAVE M2M FIELDS (FIXED: This data is now available for PDF) ---
            for name in confirmed_symptom_names:
                symptom_obj, _ = Symptom.objects.get_or_create(name=name)
                new_prescription.symptoms.add(symptom_obj)

            for name in confirmed_medicine_names:
                medicine_obj, _ = Medicine.objects.get_or_create(name=name)
                new_prescription.medicines.add(medicine_obj)

            # --- 4. SAVE FILES (Audio and Transcript) ---
            if audio_file:
                new_prescription.audio_recording.save(
                    f'rec_{patient.id}_{new_prescription.id}.webm', audio_file, save=True)
            if transcribed_text:
                transcript_content = ContentFile(
                    transcribed_text.encode('utf-8'))
                new_prescription.transcript_file.save(f'transcript_{patient.id}_{
                                                      new_prescription.id}.txt', transcript_content, save=True)

            # --- 5. GENERATE PDF (ADVANCED STYLING & DYNAMIC DATA) ---
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter

            # --- CONSTANTS FOR LAYOUT ---
            LEFT_MARGIN = 0.75 * inch
            RIGHT_MARGIN = width - 0.75 * inch
            X_COL_2_START = width / 2.0 + 0.3 * inch
            X_COL_2_DATA = X_COL_2_START + 0.8 * inch
            LINE_HEIGHT = 0.25 * inch
            SECTION_SPACE = 0.45 * inch

            # --- TEMPLATE COLORS ---
            TEAL_DARK = (0.00, 0.40, 0.45)
            TEAL_LIGHT = (0.15, 0.75, 0.80)

            # Variables doctor_full_name, doctor_spec, clinic_id are now safely defined above.

            y_cursor = height - 0.5 * inch

            # --- A. HEADER GRAPHIC AND DOCTOR INFO ---

            # 1. Background Swoop Effect (Simulated)
            p.setFillColorRGB(*TEAL_DARK)
            p.rect(0, height - 2.5*inch, width, 2.5*inch, fill=1, stroke=0)
            p.setFillColorRGB(*TEAL_LIGHT)
            p.rect(0, height - 1.8*inch, width, 0.4*inch, fill=1, stroke=0)

            # 2. Logo/Cross Symbol (Dynamic Logo Watermark and Header)
            # Watermark (Drawn first to be in background)
            if clinic_logo_path and os.path.exists(clinic_logo_path):
                try:
                    logo_reader = ImageReader(clinic_logo_path)
                    p.saveState()
                    p.setFillAlpha(0.1)  # Transparency for watermark
                    p.translate(width/2, height/2)
                    p.drawImage(logo_reader, -2.5*inch, -2.5*inch,
                                width=5*inch, height=5*inch, mask='auto')
                    p.restoreState()
                except Exception as e:
                    print(f"Error drawing logo watermark: {e}")
                    # Fallback to large Caduceus
                    p.setFillColorCMYK(0, 0, 0, 0.05)
                    p.setFont("Helvetica-Bold", 350)
                    p.drawCentredString(
                        width / 2.0, height / 2.0 - 0.5 * inch, "⚕️")
            else:
                # Default Caduceus watermark
                p.setFillColorCMYK(0, 0, 0, 0.05)
                p.setFont("Helvetica-Bold", 350)
                p.drawCentredString(width / 2.0, height /
                                    2.0 - 0.5 * inch, "⚕️")

            p.setFillColorRGB(1, 1, 1)  # Reset color for white text on header
            p.setFont("Helvetica-Bold", 14)

            # Draw Logo in Header (Small Icon)
            logo_offset = 0.5 * inch
            if clinic_logo_path and os.path.exists(clinic_logo_path):
                try:
                    p.drawImage(ImageReader(clinic_logo_path), LEFT_MARGIN,
                                height - 1.2 * inch, width=0.4 * inch, height=0.4 * inch)
                except Exception:
                    pass
            else:
                # Default Cross Icon
                p.rect(LEFT_MARGIN, height - 1.2 * inch, 0.15 *
                       inch, 0.4 * inch, fill=1, stroke=0)
                p.rect(LEFT_MARGIN - 0.12 * inch, height - 1.0 * inch,
                       0.39 * inch, 0.08 * inch, fill=1, stroke=0)

            y_cursor = height - 0.8 * inch
            p.drawString(LEFT_MARGIN + logo_offset, y_cursor, doctor_full_name)
            y_cursor -= 0.2 * inch

            p.setFont("Helvetica", 10)
            p.drawString(LEFT_MARGIN + logo_offset, y_cursor, doctor_spec)
            p.drawString(LEFT_MARGIN + logo_offset, y_cursor -
                         0.15 * inch, f"ID No: {clinic_id}")

            # Reset cursor for content below the header block
            y_cursor = height - 3.0 * inch

            # --- B/C/D/E. PATIENT DETAILS, DIAGNOSIS, MEDICATIONS (Detailed Drawing Logic) ---

            # --- Doctor/Prescription Metadata (FIX: Consistent placement) ---
            Y_DOCTOR_START = height - 1.0 * inch
            p.setFillColorRGB(1, 1, 1)
            p.setFont("Helvetica-Bold", 12)
            # Removed Rx No: and put only Prescription ID
            p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_DOCTOR_START,
                         f"Prescription ID: {new_prescription.id}")
            p.setFont("Helvetica", 10)
            p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_DOCTOR_START - 0.2 * inch,
                         f"Date: {new_prescription.date_created.strftime('%Y-%m-%d')}")

            p.setFillColorRGB(0.1, 0.1, 0.1)  # Reset for content
            p.setStrokeColorRGB(0.0, 0.5, 0.5)
            p.line(LEFT_MARGIN, y_cursor, RIGHT_MARGIN, y_cursor)
            y_cursor -= 0.3 * inch

            # --- C. PATIENT INFORMATION & VITALS (RE-INSERTED MISSING BLOCK FOR COMPLETENESS) ---
            p.setFillColorRGB(0.0, 0.5, 0.5)
            p.setFont("Helvetica-Bold", 11)
            p.drawString(LEFT_MARGIN, y_cursor, "Patient Details & Vitals:")
            y_cursor -= LINE_HEIGHT * 0.8

            p.setFont("Helvetica", 9)
            p.setFillColorRGB(0.2, 0.2, 0.2)
            Y_START_DETAILS = y_cursor

            # Name / Age and allegy
            p.drawString(LEFT_MARGIN + 0.1 * inch, Y_START_DETAILS, "Name:")
            p.drawString(LEFT_MARGIN + 1.2 * inch,
                         Y_START_DETAILS, patient.name)
            p.drawString(X_COL_2_START, Y_START_DETAILS, "Age:")
            p.drawString(X_COL_2_DATA, Y_START_DETAILS,
                         f"{patient.age or 'N/A'}")

            Y_START_DETAILS -= LINE_HEIGHT

            # Phone / Gender
            p.drawString(LEFT_MARGIN + 0.1 * inch, Y_START_DETAILS, "Phone:")
            p.drawString(LEFT_MARGIN + 1.2 * inch,
                         Y_START_DETAILS, patient.phone or 'N/A')
            p.drawString(X_COL_2_START, Y_START_DETAILS, "Gender:")
            p.drawString(X_COL_2_DATA, Y_START_DETAILS,
                         patient.gender or 'N/A')
            Y_START_DETAILS -= LINE_HEIGHT

            # Email / Weight
            p.drawString(LEFT_MARGIN + 0.1 * inch, Y_START_DETAILS, "Email:")
            p.drawString(LEFT_MARGIN + 1.2 * inch,
                         Y_START_DETAILS, patient.email or 'N/A')
            p.drawString(X_COL_2_START, Y_START_DETAILS, "Weight:")
            p.drawString(X_COL_2_DATA, Y_START_DETAILS,
                         f"{patient.weight or 'N/A'} kg")
            Y_START_DETAILS -= LINE_HEIGHT

            # Blood Grp / BP
            p.drawString(LEFT_MARGIN + 0.1 * inch,
                         Y_START_DETAILS, "Blood Grp:")
            p.drawString(LEFT_MARGIN + 1.2 * inch, Y_START_DETAILS,
                         patient.blood_group or 'N/A')
            p.drawString(X_COL_2_START, Y_START_DETAILS, "BP:")
            p.drawString(X_COL_2_DATA, Y_START_DETAILS,
                         new_prescription.blood_pressure or 'N/A')
            Y_START_DETAILS -= LINE_HEIGHT

            # 🧾 Allergy
            p.drawString(LEFT_MARGIN + 0.1 * inch, Y_START_DETAILS, "Allergy:")
            p.drawString(LEFT_MARGIN + 1.2 * inch, Y_START_DETAILS,
                         f"{patient.allergy or 'N/A'}")
            Y_START_DETAILS -= LINE_HEIGHT
            # --- ADDRESS ---
            p.drawString(LEFT_MARGIN + 0.1 * inch, Y_START_DETAILS, "Address:")
            address_text = patient.address or "N/A"
            address_text_object = p.beginText(
                LEFT_MARGIN + 1.2 * inch, Y_START_DETAILS)
            address_text_object.setFont("Helvetica", 9)
            address_text_object.setLeading(10)
            MAX_ADDRESS_WRAP_WIDTH = RIGHT_MARGIN - (LEFT_MARGIN + 1.2 * inch)
            words = address_text.split(' ')
            current_line = ""
            for word in words:
                line_to_check = (current_line + " " + word).strip()
                if p.stringWidth(line_to_check, "Helvetica", 9) > MAX_ADDRESS_WRAP_WIDTH:
                    address_text_object.textLine(current_line.strip())
                    current_line = word
                else:
                    current_line += (" " + word)
            if current_line:
                address_text_object.textLine(current_line.strip())
            p.drawText(address_text_object)
            y_cursor = Y_START_DETAILS - (LINE_HEIGHT * 2.0)
            p.line(LEFT_MARGIN, y_cursor, RIGHT_MARGIN, y_cursor)
            y_cursor -= SECTION_SPACE
            # --- END C. PATIENT INFO ---

            # --- D. DIAGNOSIS (Symptoms) ---
            p.setFillColorRGB(0.1, 0.1, 0.1)
            p.setFont("Helvetica-Bold", 12)
            # Keep Diagnosis section as requested
            p.drawString(LEFT_MARGIN, y_cursor,
                         "A. Diagnosis / Confirmed Symptoms:")
            y_cursor -= LINE_HEIGHT

            # FIX: Use the local variable confirmed_symptom_names
            symptom_text = ", ".join(
                confirmed_symptom_names) if confirmed_symptom_names else "No symptoms recorded by doctor."
            p.setFont("Helvetica", 10)
            p.drawString(LEFT_MARGIN + 0.2 * inch, y_cursor, symptom_text)
            y_cursor -= LINE_HEIGHT * 2.0

            # --- E. MEDICATIONS (Med Info Block) ---
            p.setFillColorRGB(0.1, 0.1, 0.1)
            p.setFont("Helvetica-Bold", 12)
            # New Heading for Medicine Info (Removed Rx:)
            p.drawString(LEFT_MARGIN, y_cursor,
                         "B. Medications / Medicine Info:")
            y_cursor -= LINE_HEIGHT

            p.setFont("Helvetica", 11)
            if confirmed_medicine_names:
                for med_name in confirmed_medicine_names:
                    p.drawString(LEFT_MARGIN + 0.4 * inch, y_cursor,
                                 f"• {med_name} - [Instructions: TBD, e.g., 500mg, Twice a Day]")
                    y_cursor -= LINE_HEIGHT * 1.5
            else:
                p.drawString(LEFT_MARGIN + 0.4 * inch, y_cursor,
                             "No medications prescribed.")
                y_cursor -= LINE_HEIGHT * 1.5

            y_cursor -= LINE_HEIGHT * 2.0

            # --- F. CONSULTATION NOTES ---
            y_cursor -= SECTION_SPACE * 0.8
            p.setStrokeColorRGB(0.8, 0.8, 0.8)
            p.line(LEFT_MARGIN, y_cursor, RIGHT_MARGIN, y_cursor)
            y_cursor -= 0.3 * inch

            p.setFillColorRGB(0.1, 0.1, 0.1)
            p.setFont("Helvetica-Bold", 11)
            p.drawString(LEFT_MARGIN, y_cursor,
                         "C. Consultation Notes (Transcription):")
            y_cursor -= 0.1 * inch

            # Add transcribed text
            if transcribed_text:
                text_object = p.beginText(LEFT_MARGIN + 0.1 * inch, y_cursor)
                text_object.setFont("Helvetica", 9)
                text_object.setLeading(10)

                # Simple line break insertion for ReportLab
                lines = transcribed_text.split('\n')
                for line in lines:
                    text_object.textLine(line)

                p.drawText(text_object)
                y_cursor -= LINE_HEIGHT * (len(lines) + 1)
            else:
                p.setFont("Helvetica", 9)
                p.drawString(LEFT_MARGIN + 0.1 * inch, y_cursor,
                             "No transcription available.")
                y_cursor -= LINE_HEIGHT

            y_cursor -= SECTION_SPACE * 1.5

            # --- G. FOOTER AND SIGNATURE ---

            # --- G. FOOTER AND SIGNATURE ---

            # 1. Draw the Signature Line
            p.setStrokeColorRGB(0.5, 0.5, 0.5)
            # Line position: x1, y1 to x2, y2
            SIG_LINE_Y = 1.5 * inch
            p.line(RIGHT_MARGIN - 2.5 * inch, SIG_LINE_Y, 
                   RIGHT_MARGIN - 0.5 * inch, SIG_LINE_Y)

            # 2. Logic: Paste the Signature Image if available
            if doctor and doctor.signature:
                try:
                    sig_path = doctor.signature.path
                    if os.path.exists(sig_path):
                        # Calculate position to put the image ON TOP of the line
                        # x centered roughly over the line, y just above the line
                        sig_width = 1.5 * inch
                        sig_height = 0.5 * inch
                        sig_x = RIGHT_MARGIN - 2.25 * inch # Start slightly left of the line start
                        sig_y = SIG_LINE_Y + 0.05 * inch   # Just above the line
                        
                        p.drawImage(ImageReader(sig_path), sig_x, sig_y, 
                                    width=sig_width, height=sig_height, mask='auto')
                except Exception as e:
                    print(f"Error drawing signature: {e}")

            # 3. Label below the line
            p.setFillColorRGB(0.2, 0.2, 0.2)
            p.setFont("Helvetica", 9)
            p.drawRightString(RIGHT_MARGIN, 1.3 * inch, "Doctor's Signature")

            # --- FOOTER BAR (Dynamic Clinic Info) ---
            p.setFillColorRGB(*TEAL_DARK)
            p.rect(0, 0, width, 1.2 * inch, fill=1, stroke=0)

            p.setFillColorRGB(1, 1, 1)  # White text
            p.setFont("Helvetica-Bold", 10)
            p.drawCentredString(width / 2.0, 1.0 * inch, clinic_name)

            p.setFont("Helvetica", 8)
            # Split address string by the pipe '|' delimiter
            address_parts = [part.strip() for part in clinic_address.split('|')]

            if len(address_parts) >= 3:
                p.drawString(LEFT_MARGIN, 0.7 * inch, address_parts[0])
                p.drawCentredString(width / 2.0, 0.7 * inch, address_parts[1])
                p.drawRightString(RIGHT_MARGIN, 0.7 * inch, address_parts[2])
            else:
                p.drawCentredString(width / 2.0, 0.7 * inch, clinic_address)

            # Finalize the PDF
            p.showPage()
            p.save()
            pdf_data = buffer.getvalue()
            buffer.close()

            # --- 6. SAVE PDF TO THE MODEL AND RETURN JSON ---
            # filename = f'prescription_{patient.id}_{new_prescription.id}.pdf'
            # new_prescription.prescription_file.save(
            #     filename, ContentFile(pdf_data), save=True)

            folder_name = f"{patient.name}_{patient.phone}".replace(" ", "_")
            filename = f"{
                folder_name}/prescription_{patient.id}_{new_prescription.id}.pdf"

            # Save PDF file into that folder
            new_prescription.prescription_file.save(
                filename, ContentFile(pdf_data), save=True)

            return JsonResponse({
                'status': 'success',
                'message': 'Prescription verified and saved!',
                'prescription_id': new_prescription.id
            })

    return render(request, "prescription.html", {})


@login_required
def prescription_detail(request, prescription_id):
    # ... (existing code) ...
    try:
        prescription = Prescription.objects.get(id=prescription_id)
    except Prescription.DoesNotExist:
        return redirect('history')

    return render(request, 'prescription_detail.html', {'prescription': prescription})


# --- MISSING PLACEHOLDER VIEWS (REQUIRED BY urls.py) ---
@csrf_exempt
def get_previous_medication(request):
    """Placeholder for the 'get_previous_medication' AJAX endpoint."""
    if request.method == 'GET':
        # Logic to fetch past medication based on patient data
        dummy_medications = [{"name": "Amoxicillin", "dose": "500mg"}]
        return JsonResponse({'status': 'success', 'medications': dummy_medications})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)


@csrf_exempt
def update_medication(request):
    """Placeholder for the 'update_medication' AJAX endpoint."""
    if request.method == 'POST':
        # Logic to update medication.
        return JsonResponse({'status': 'success', 'message': 'Medication updated.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)


# --- OTHER VIEWS REMAIN THE SAME ---
def home(request): return render(request, "home.html")
# ... (history, help, signup_view, login_view, logout_view, profile, send_sms, send_email, edit_profile, contact views remain the same) ...


@login_required
def history(request):
    """
    Handles displaying the history page with search and pagination.
    FILTERED: Only shows prescriptions created by the currently logged-in doctor.
    """
    # 1. Security Check: Ensure the user has a Doctor profile
    try:
        current_doctor = request.user.doctor
    except Doctor.DoesNotExist:
        messages.error(request, "Access Restricted: You must be a registered doctor to view history.")
        return redirect('profile')

    # Get the search query and date range from the GET request
    query = request.GET.get('q', '')
    start_date = request.GET.get('startDate')
    end_date = request.GET.get('endDate')

    # 2. FILTER LOGIC: Get only THIS doctor's prescriptions
    # We use .filter(doctor=current_doctor) instead of .all()
    all_prescriptions = Prescription.objects.filter(doctor=current_doctor).order_by('-date_created')

    # If a search query is provided, filter the prescriptions by patient name
    if query:
        all_prescriptions = all_prescriptions.filter(
            patient__name__icontains=query)

    # If date range is provided, filter the prescriptions
    if start_date and end_date:
        all_prescriptions = all_prescriptions.filter(
            date_created__range=[start_date, end_date])

    # Set up pagination with 7 items per page
    paginator = Paginator(all_prescriptions, 7)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Pass the paginated list, and the search/date values back to the template
    context = {
        'page_obj': page_obj,
        'query': query,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'history.html', context)

def help(request):
    """
    Renders the help/FAQ page.
    """
    return render(request, 'help.html')


def signup_view(request):
    if request.method == 'POST':
        user_form = UserForm(request.POST)
        doctor_form = DoctorForm(request.POST)
        if user_form.is_valid() and doctor_form.is_valid():
            user = user_form.save(commit=False)
            user.set_password(user_form.cleaned_data['password'])
            user.save()
            Doctor.objects.create(user=user, **doctor_form.cleaned_data)
            login(request, user)
            return redirect('profile')
    else:
        user_form, doctor_form = UserForm(), DoctorForm()
    return render(request, 'signup.html', {'user_form': user_form, 'doctor_form': doctor_form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('profile')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile(request):
    try:
        doctor = request.user.doctor
    except Doctor.DoesNotExist:
        messages.warning(request, "Please complete your profile details.")
        return redirect('edit-profile')

    return render(request, 'profile.html', {'doctor': doctor})


@login_required
def edit_profile(request):
    try:
        doctor_profile = request.user.doctor
    except Doctor.DoesNotExist:
        doctor_profile = Doctor.objects.create(user=request.user)

    if request.method == 'POST':
        form = DoctorProfileUpdateForm(
            request.POST, request.FILES, instance=doctor_profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')
    else:
        form = DoctorProfileUpdateForm(instance=doctor_profile)

    return render(request, 'edit_profile.html', {'form': form})


# Placeholder for SMS


@login_required
def send_sms(request, prescription_id):
    """
    This view is called by the frontend's AJAX request when the 'Send' button is clicked.
    """
    if request.method == 'POST':
        try:
            prescription = Prescription.objects.get(id=prescription_id)
            patient_phone = prescription.patient.phone

            if not patient_phone:
                return JsonResponse({'status': 'error', 'message': 'Patient phone number is not available.'}, status=400)

            pdf_url = request.build_absolute_uri(
                prescription.prescription_file.url)

            # --- TWILIO SMS LOGIC ---
            try:
                client = Client(settings.TWILIO_ACCOUNT_SID,
                                settings.TWILIO_AUTH_TOKEN)
                doctor_name = f"Dr. {
                    prescription.doctor.first_name}" if prescription.doctor else "the clinic"
                message_body = f"Hello {prescription.patient.name}, your prescription from {
                    doctor_name} is ready. View it here: {pdf_url}"

                message = client.messages.create(
                    body=message_body,
                    from_=settings.TWILIO_PHONE_NUMBER,
                    to=patient_phone
                )
                return JsonResponse({'status': 'success', 'message': f"SMS sent successfully to {patient_phone}."})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'Failed to send SMS via Twilio.'}, status=500)

        except Prescription.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Prescription not found.'}, status=404)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


# home/views.py

@login_required
def send_email(request, prescription_id):
    print("\n--- [DEBUG] SEND EMAIL VIEW TRIGGERED ---")
    if request.method == 'POST':
        try:
            print(f"[DEBUG] Finding prescription with ID: {prescription_id}")
            prescription = Prescription.objects.get(id=prescription_id)
            patient_email = prescription.patient.email
            print(f"[DEBUG] Found patient email: '{patient_email}'")

            if not patient_email:
                print("[DEBUG] ERROR: Patient email is blank.")
                return JsonResponse({'status': 'error', 'message': 'Patient email address is not available.'}, status=400)

            if not prescription.prescription_file or not prescription.prescription_file.path:
                print(
                    "[DEBUG] ERROR: Prescription PDF file not found or not saved to disk.")
                return JsonResponse({'status': 'error', 'message': 'No prescription PDF found to send.'}, status=400)

            print(f"[DEBUG] PDF file path found: {
                  prescription.prescription_file.path}")

            try:
                print("[DEBUG] Preparing to send email...")
                doctor_name = f"Dr. {
                    prescription.doctor.first_name}" if prescription.doctor else "the clinic"
                subject = f"Your Prescription from {doctor_name}"
                body = f"Hello {
                    prescription.patient.name},\n\nPlease find your prescription attached.\n\nThank Thank you,\n{doctor_name}"

                email = EmailMessage(
                    subject, body, settings.EMAIL_HOST_USER, [patient_email])

                print("[DEBUG] Attaching PDF file to email...")
                email.attach_file(prescription.prescription_file.path)

                print("[DEBUG] Executing email.send()...")
                email.send()

                print("[DEBUG] SUCCESS: email.send() command finished.")
                return JsonResponse({'status': 'success', 'message': f'Email sent successfully to {patient_email}.'})
            except Exception as e:
                print(
                    f"\n !!! [DEBUG] CRITICAL ERROR during email sending: {e}\n")
                return JsonResponse({'status': 'error', 'message': 'Failed to send email. Check server log for details.'}, status=500)

        except Prescription.DoesNotExist:
            print(f"[DEBUG] ERROR: Prescription with ID {
                  prescription_id} not found.")
            return JsonResponse({'status': 'error', 'message': 'Prescription not found.'}, status=404)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

# Replace your existing contact view with this one


def contact(request):
    """
    Handles displaying and processing the contact form with server-side validation.
    """
    if request.method == 'POST':
        form = ContactForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request, 'Your message has been sent successfully! We will get back to you shortly.')
            return redirect('contact')
    else:
        form = ContactForm()

    return render(request, 'contact.html', {'form': form})


# home/views.py (Implementation of analyze_prescription_view)

@csrf_exempt
def analyze_prescription_view(request):
    """
    Handles the AJAX call to predict medicines using the Gemini LLM
    based on confirmed symptoms and patient data.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            confirmed_symptom_names = data.get('confirmed_symptoms', [])
            patient_info = data.get('patient_info', {})

            if not confirmed_symptom_names:
                return JsonResponse({'status': 'error', 'message': 'No symptoms provided for medicine prediction.'}, status=400)

            # 🔨 Prepare data for LLM
            symptoms_data_for_llm = {"symptoms": [
                {"name": s} for s in confirmed_symptom_names]}

            #  Gemini Call for Medicine Prediction
            med_suggestions = predict_medicines_from_symptoms(
                symptoms_data_for_llm, patient_info)

            return JsonResponse({'status': 'success', 'suggestions': med_suggestions})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Medicine Prediction Error: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@csrf_exempt
def save_suggestion_view(request):
    """
    Saves the confirmed medication suggestions to the Prescription model's M2M field.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            prescription_id = data.get('prescription_id')
            confirmed_med_names = data.get('confirmed_meds', [])

            if not prescription_id:
                return JsonResponse({'status': 'error', 'message': 'Missing prescription ID.'}, status=400)

            prescription = get_object_or_404(Prescription, id=prescription_id)

            for name in confirmed_med_names:
                clean_name = name.strip().capitalize()
                if clean_name:
                    med_obj, _ = Medicine.objects.get_or_create(
                        name=clean_name)
                    prescription.medicines.add(med_obj)

            return JsonResponse({'status': 'success', 'message': 'Medication suggestions saved successfully.'})

        except Prescription.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Prescription not found.'}, status=404)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Save Error: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def get_previous_medication(request):
    """
    Fetch all saved prescription PDFs for a given patient (by name + phone).
    Returns a list of file URLs or an error message.
    """
    try:
        phone = request.GET.get("phone", "").strip()
        name = request.GET.get("patientName", "").strip()

        if not phone or not name:
            return JsonResponse({
                "status": "error",
                "message": "Missing patient name or phone number."
            }, status=400)

        # Folder path: media/prescriptions/<name>_<phone>/
        folder_name = f"{name}_{phone}".replace(" ", "_")
        folder_path = os.path.join(
            settings.MEDIA_ROOT, "prescriptions", folder_name)

        if not os.path.exists(folder_path):
            return JsonResponse({
                "status": "not_found",
                "message": "No previous prescriptions found for this patient."
            })

        # Collect only .pdf files
        pdf_files = [
            f"/media/prescriptions/{folder_name}/{f}"
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf")
        ]

        if not pdf_files:
            return JsonResponse({
                "status": "not_found",
                "message": "No prescription files found."
            })

        return JsonResponse({
            "status": "success",
            "message": f"{len(pdf_files)} prescription(s) found.",
            "files": pdf_files
        })

    except Exception as e:
        print("❌ Error in get_previous_medication:", e)
        return JsonResponse({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }, status=500)
