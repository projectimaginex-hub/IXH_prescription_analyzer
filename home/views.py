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
from .forms import UserForm, DoctorForm, DoctorProfileUpdateForm  # UPDATED
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Patient, Prescription, Doctor, Symptom, Medicine, Audio, ContactSubmission
from .llm_utils import extract_symptoms_from_text  # ADDED LLM Import
from django.db import transaction  # ADDED
from .models import Patient, Prescription, Doctor, Symptom, Medicine, Audio, ContactSubmission
from .llm_utils import extract_symptoms_from_text, predict_medicines_from_symptoms # 👈 MODIFIED: Added medicine prediction
from django.db import transaction

from twilio.rest import Client

# --- ASSEMBLYAI API CONFIG ---
ASSEMBLYAI_UPLOAD_ENDPOINT = 'https://api.assemblyai.com/v2/upload'
ASSEMBLYAI_TRANSCRIPT_ENDPOINT = 'https://api.assemblyai.com/v2/transcript'

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


# --- CORRECTED PRESCRIPTION VIEW (Handling Symptoms) ---

@login_required
def prescription(request):
    """
    Handles the 'Verify & Save' submission via an asynchronous request (AJAX).
    UPDATED: Now processes the confirmedSymptoms field from the frontend.
    """
    if request.method == 'POST':
        # --- 1. GATHER AND VALIDATE DATA ---
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
   

        # --- NEW: Get the confirmed symptoms list ---
        confirmed_symptoms_str = request.POST.get('confirmedSymptoms', '')
        confirmed_symptom_names = [
            s.strip() for s in confirmed_symptoms_str.split(',') if s.strip()]

        age_val = int(age) if age and age.isdigit() else None
        weight_val = float(weight) if weight and weight.replace(
            '.', '', 1).isdigit() else None

        with transaction.atomic():  # Use a transaction for reliability
            # --- 2. CREATE DATABASE OBJECTS ---
           # --- ✅ NEW CODE: Use update_or_create to ensure fields are refreshed ---
            patient, created = Patient.objects.update_or_create(
    # Fields used for strict lookup (IDENTIFYING existing record):
        phone=phone, 
        name=patient_name, # 👈 NEW: Use name for lookup to prevent cross-contamination
        
        # Fields to update if existing, or set if created:
        defaults={
            'age': age_val,
            'email': email,
            'gender': gender,
            'blood_group': blood_group,
            'weight': weight_val,
           
        }
    )

            try:
                doctor = request.user.doctor
            except Doctor.DoesNotExist:
                doctor = None

            new_prescription = Prescription.objects.create(
                patient=patient, doctor=doctor, blood_pressure=blood_pressure,
                transcribed_text=transcribed_text, is_verified=True, verified_at=timezone.now()
)

            # --- 3. SAVE SYMPTOMS TO M2M FIELD ---
            for name in confirmed_symptom_names:
                # 1. Get or create the Symptom object
                symptom_obj, _ = Symptom.objects.get_or_create(name=name)
                # 2. Add the M2M relationship
                new_prescription.symptoms.add(symptom_obj) 
            # ----------------------------------------------------

            # --- 4. SAVE THE FILES (Audio and Transcript) ---
            # NOTE: I am using the fields you defined in models.py (audio_recording, transcript_file)
            if audio_file:
                new_prescription.audio_recording.save(
                    f'rec_{patient.id}_{new_prescription.id}.webm', audio_file, save=True)

            if transcribed_text:
                transcript_content = ContentFile(
                    transcribed_text.encode('utf-8'))
                new_prescription.transcript_file.save(
                    f'transcript_{patient.id}_{new_prescription.id}.txt', transcript_content, save=True)
# --- 5. GENERATE PDF (MATCHING TEMPLATE FORMAT) ---
        # home/views.py (Replace the PDF generation section in prescription(request) view)

        # --- 5. GENERATE PDF (ENHANCED CLINICAL DESIGN) ---
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # --- CONSTANTS FOR LAYOUT ---
        LEFT_MARGIN = 0.7 * inch
        RIGHT_MARGIN = width - 0.7 * inch
        LINE_COLOR = 0xCCCCCC # Light gray hex color for dividers
        ACCENT_COLOR = 0x1E88E5 # Blue hex color for accents

        # --- 1. CLINIC HEADER (Modernized) ---
        p.setFillColorRGB(0.1, 0.1, 0.1) # Dark gray text
        p.setFont("Helvetica-Bold", 18)
        p.drawCentredString(width / 2.0, height - 0.5 * inch, "IMAGINEX HEALTH CLINIC")

        p.setFont("Helvetica", 8)
        p.setFillColorRGB(0.4, 0.4, 0.4) # Lighter gray for contact info
        p.drawCentredString(width / 2.0, height - 0.75 * inch, 
                        "Kolkata Medical, India | youremail@companyname.com | +91 98765 43210")

        p.setStrokeColorRGB(0.8, 0.8, 0.8)
        p.line(LEFT_MARGIN, height - 1.0 * inch, RIGHT_MARGIN, height - 1.0 * inch)

        # --- 2. DOCTOR / PRESCRIPTION METADATA ---
        Y_DOCTOR = height - 1.3 * inch

        p.setFillColorRGB(0.1, 0.1, 0.1)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(LEFT_MARGIN, Y_DOCTOR, "Prescribing Doctor:")

        # Doctor Info
        doctor_full_name = f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Dr. ABC DEF"
        doctor_spec = doctor.specialization if doctor and doctor.specialization else "General Physician"
        p.setFont("Helvetica", 10)
        p.drawString(LEFT_MARGIN, Y_DOCTOR - 0.2 * inch, doctor_full_name)
        p.drawString(LEFT_MARGIN, Y_DOCTOR - 0.4 * inch, doctor_spec)

        # Prescription ID and Date (Aligned Right)
        p.setFont("Helvetica", 10)
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_DOCTOR, "Prescription No.:")
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_DOCTOR - 0.2 * inch, "Date:")

        p.setFont("Helvetica-Bold", 10)
        p.drawString(RIGHT_MARGIN - 1.5 * inch, Y_DOCTOR, str(new_prescription.id))
        p.drawString(RIGHT_MARGIN - 1.5 * inch, Y_DOCTOR - 0.2 * inch, 
                    new_prescription.date_created.strftime('%Y-%m-%d'))

        p.line(LEFT_MARGIN, height - 2.0 * inch, RIGHT_MARGIN, height - 2.0 * inch)

        # --- 3. PATIENT INFORMATION & VITALS ---
        Y_PATIENT_START = height - 2.3 * inch
        p.setFont("Helvetica-Bold", 12)
        p.drawString(LEFT_MARGIN, Y_PATIENT_START, "Patient Details:")

        p.setFont("Helvetica", 10)
        p.drawString(LEFT_MARGIN + 0.1 * inch, Y_PATIENT_START - 0.25 * inch, f"Name: {patient.name}")
        p.drawString(LEFT_MARGIN + 0.1 * inch, Y_PATIENT_START - 0.45 * inch, f"Age: {patient.age or 'N/A'}")
        p.drawString(LEFT_MARGIN + 0.1 * inch, Y_PATIENT_START - 0.65 * inch, f"Gender: {patient.gender or 'N/A'}")
        # NOTE: Address field drawing is omitted as requested.
        
        
        p.drawString(LEFT_MARGIN + 0.1 * inch, Y_PATIENT_START - 0.85 * inch, f"Address: {patient.address or 'N/A'}") 

        # Vitals Block (Aligned Right/Middle)
        p.setFont("Helvetica-Bold", 10)
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.25 * inch, "Vitals:")
        p.setFont("Helvetica", 10)
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.45 * inch, f"BP: {new_prescription.blood_pressure or 'N/A'}")
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.65 * inch, f"Weight: {patient.weight or 'N/A'} kg")
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.85 * inch, f"Blood Grp: {patient.blood_group or 'N/A'}")


        # NOTE: Moved separator line down to accommodate the extra Address line
        p.line(LEFT_MARGIN, height - 3.6 * inch, RIGHT_MARGIN, height - 3.6 * inch)

        # Vitals Block (Aligned Right/Middle)
        p.setFont("Helvetica-Bold", 10)
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.25 * inch, "Vitals:")
        p.setFont("Helvetica", 10)
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.45 * inch, f"BP: {new_prescription.blood_pressure or 'N/A'}")
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.65 * inch, f"Weight: {patient.weight or 'N/A'} kg")
        p.drawString(RIGHT_MARGIN - 2.5 * inch, Y_PATIENT_START - 0.85 * inch, f"Blood Grp: {patient.blood_group or 'N/A'}")


        p.line(LEFT_MARGIN, height - 3.4 * inch, RIGHT_MARGIN, height - 3.4 * inch) # Separator

        # --- 4. DIAGNOSIS (Symptoms) ---
        Y_DIAGNOSIS = height - 3.7 * inch
        p.setFillColorCMYK(0, 0, 0, 0.7) # Darker text
        p.setFont("Helvetica-Bold", 12)
        p.drawString(LEFT_MARGIN, Y_DIAGNOSIS, "A. Confirmed Symptoms (Diagnosis):")

        symptom_text = ", ".join(confirmed_symptom_names) if confirmed_symptom_names else "No symptoms recorded by doctor."
        p.setFont("Helvetica", 10)
        p.drawString(LEFT_MARGIN + 0.2 * inch, Y_DIAGNOSIS - 0.2 * inch, symptom_text)

        # --- 5. MEDICATIONS ---
        Y_MEDICATIONS = Y_DIAGNOSIS - 0.7 * inch
        p.setFillColorCMYK(0, 0, 0, 0.7)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(LEFT_MARGIN, Y_MEDICATIONS, "B. Medications (℞):")

        medicines = new_prescription.medicines.all()
        y_cursor = Y_MEDICATIONS - 0.2 * inch
        p.setFont("Helvetica", 10)

        if medicines:
            for med in medicines:
                p.drawString(LEFT_MARGIN + 0.2 * inch, y_cursor, 
                            f"• {med.name} - [Instructions: TBD]") # Using bullet point for clarity
                y_cursor -= 0.2 * inch
        else:
            p.drawString(LEFT_MARGIN + 0.2 * inch, y_cursor, "No medications prescribed.")
            y_cursor -= 0.2 * inch


        # --- 6. CONSULTATION NOTES (Transcription) ---
        Y_NOTES_START = y_cursor - 0.4 * inch
        p.setFont("Helvetica-Bold", 12)
        p.drawString(LEFT_MARGIN, Y_NOTES_START, "C. Consultation Notes:")

        notes = new_prescription.transcribed_text or "No detailed transcription available."

        # Use ReportLab's text object for flowing text
        Y_TEXT_START = Y_NOTES_START - 0.1 * inch
        text_object = p.beginText(LEFT_MARGIN + 0.2 * inch, Y_TEXT_START)
        text_object.setFont("Helvetica", 9)
        text_object.setLeading(12)

        # Max width for text block calculation
        max_width = RIGHT_MARGIN - (LEFT_MARGIN + 0.2 * inch) 

        current_line_parts = []
        current_width = 0
        line_space = p.stringWidth(" ", "Helvetica", 9)
        notes_y_position = Y_TEXT_START

        for word in notes.split():
            word_width = p.stringWidth(word, "Helvetica", 9)
            if current_width + word_width + line_space > max_width:
                text_object.textLine(" ".join(current_line_parts))
                notes_y_position -= 12
                current_line_parts = [word]
                current_width = word_width
            else:
                current_line_parts.append(word)
                current_width += (word_width + line_space)

        if current_line_parts:
            text_object.textLine(" ".join(current_line_parts))
            notes_y_position -= 12

        p.drawText(text_object)

        # --- 7. SIGNATURE / FOOTER ---
        p.setStrokeColorRGB(0.5, 0.5, 0.5) # Gray line
        p.line(RIGHT_MARGIN - 2.5 * inch, 1.5 * inch, RIGHT_MARGIN - 0.5 * inch, 1.5 * inch) # Signature Line

        p.setFillColorRGB(0.1, 0.1, 0.1)
        p.setFont("Helvetica-Bold", 10)
        p.drawRightString(RIGHT_MARGIN - 0.5 * inch, 1.3 * inch, doctor_full_name)
        p.drawRightString(RIGHT_MARGIN - 0.5 * inch, 1.15 * inch, "Dr. Signature")

        p.setFont("Helvetica-Oblique", 8)
        p.setFillColorRGB(0.6, 0.6, 0.6) # Light gray
        p.drawCentredString(width / 2.0, 0.5 * inch, 
                            "Digitally verified prescription - IMAGINEX HEALTH CLINIC")

        # Finalize the PDF
        p.showPage()
        p.save()
        pdf_data = buffer.getvalue()
        buffer.close()

# --- 8. SAVE PDF TO THE MODEL AND RETURN JSON ---
# ... (File saving logic remains the same) ...

        # --- 6. SAVE PDF TO THE MODEL AND RETURN JSON ---
        filename = f'prescription_{patient.id}_{new_prescription.id}.pdf'
        new_prescription.prescription_file.save(filename, ContentFile(pdf_data), save=True)
        
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
    """
    # Get the search query and date range from the GET request
    query = request.GET.get('q', '')
    start_date = request.GET.get('startDate')
    end_date = request.GET.get('endDate')

    # Start with all prescriptions, ordered by the most recent
    all_prescriptions = Prescription.objects.all().order_by('-date_created')

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
        doctor = None
    return render(request, 'profile.html', {'doctor': doctor})

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
                    prescription.patient.name},\n\nPlease find your prescription attached.\n\nThank you,\n{doctor_name}"

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

# home/views.py
# ... (other imports and views) ...


@login_required
def edit_profile(request):
    # Ensure the user has a doctor profile, redirecting if not
    doctor_profile = get_object_or_404(Doctor, user=request.user)

    if request.method == 'POST':
        # Pass 'instance=doctor_profile' to update the existing record
        form = DoctorProfileUpdateForm(
            request.POST, request.FILES, instance=doctor_profile)
        if form.is_valid():
            form.save()
            # Redirect back to the profile page on success
            return redirect('profile')
    else:
        # Pre-populate the form with the doctor's current data
        form = DoctorProfileUpdateForm(instance=doctor_profile)

    return render(request, 'edit_profile.html', {'form': form})

# Replace your existing contact view with this one


def contact(request):
    """
    Handles displaying and processing the contact form with server-side validation.
    """
    if request.method == 'POST':
        # Create a form instance and populate it with data from the request
        form = ContactForm(request.POST)

        # Check if the form is valid
        if form.is_valid():
            # Save the valid data to the database
            form.save()
            messages.success(
                request, 'Your message has been sent successfully! We will get back to you shortly.')
            # Redirect to prevent form resubmission on page refresh
            return redirect('contact')
        # If the form is invalid, the view will fall through and re-render the page
        # with the form instance containing the error messages.
    else:
        # If it's a GET request, create a blank form instance
        form = ContactForm()

    return render(request, 'contact.html', {'form': form})


# home/views.py (Add this function)

# Make sure you have the necessary imports at the top of home/views.py:
# from .llm_utils import predict_medicines_from_symptoms
# from django.views.decorators.csrf import csrf_exempt
# import json

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
            # The LLM utility expects symptoms in a specific JSON format
            symptoms_data_for_llm = {"symptoms": [{"name": s} for s in confirmed_symptom_names]}
            
            #  Gemini Call for Medicine Prediction
            med_suggestions = predict_medicines_from_symptoms(symptoms_data_for_llm, patient_info)
            
            return JsonResponse({'status': 'success', 'suggestions': med_suggestions})

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Medicine Prediction Error: {str(e)}'}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

# ... (Keep all your other existing views) ...


# home/views.py (Add this function)

# Make sure you have the necessary imports at the top of home/views.py:
# from django.views.decorators.csrf import csrf_exempt
# import json

@csrf_exempt
def save_suggestion_view(request):
    """
    Placeholder for the 'api/save-suggestion/' AJAX endpoint.
    This view saves the AI-suggested or doctor-confirmed medications 
    to the Prescription model.
    """
    if request.method == 'POST':
        try:
            # In a real implementation, you would:
            # 1. Parse data = json.loads(request.body.decode('utf-8'))
            # 2. Extract prescription ID and confirmed medication list.
            # 3. Save medicines to the Prescription's ManyToMany field.

            return JsonResponse({'status': 'success', 'message': 'Medication suggestions saved successfully.'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Save Error: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

# ... (Keep all your other existing views) ...

