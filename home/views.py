import io
import time
import requests
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from .models import Patient, Prescription, Doctor
from .forms import UserForm, DoctorForm
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm

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
                polling_response = requests.get(polling_endpoint, headers=headers, verify=False)
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

# --- CORRECTED PRESCRIPTION VIEW ---
@login_required
def prescription(request):
    """
    Handles the 'Verify & Save' submission with corrected logic.
    """
    if request.method == 'POST':
        # --- 1. GATHER AND VALIDATE DATA ---
        patient_name = request.POST.get('patientName')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('bloodGrp')
        weight = request.POST.get('weight')
        blood_pressure = request.POST.get('bp')
        transcribed_text = request.POST.get('transcriptionText')

        age_val = int(age) if age and age.isdigit() else None
        weight_val = float(weight) if weight and weight.replace('.', '', 1).isdigit() else None

        # --- 2. CREATE AND SAVE THE DATABASE OBJECTS ---
        patient = Patient.objects.create(
            name=patient_name, phone=phone, age=age_val,
            gender=gender, blood_group=blood_group, weight=weight_val
        )

        try:
            doctor = request.user.doctor
        except Doctor.DoesNotExist:
            doctor = None

        # Create and save the Prescription. This is the crucial step.
        # After this line runs, all fields are guaranteed to have a value.
        new_prescription = Prescription.objects.create(
            patient=patient,
            doctor=doctor,
            blood_pressure=blood_pressure,
            transcribed_text=transcribed_text,
            is_verified=True,
            verified_at=timezone.now()
        )

        # --- 3. GENERATE THE PDF (NOW THAT DATA IS SAVED) ---
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Header
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(width / 2.0, height - 1 * inch, "🏥 IMAGINEX HEALTH CLINIC")
        p.setFont("Helvetica", 11)
        p.drawCentredString(width / 2.0, height - 1.2 * inch, "123 Health Street, Bengaluru, India | +91 98765 43210")
        p.line(0.8 * inch, height - 1.3 * inch, width - 0.8 * inch, height - 1.3 * inch)

        # Doctor Info (Now using the reliable data from the saved object)
        doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Dr. ABC DEF"
        specialization = getattr(doctor, "specialization", "General Physician") if doctor else "General Physician"
        p.setFont("Helvetica-Bold", 13)
        p.drawString(1 * inch, height - 1.7 * inch, doctor_name)
        p.setFont("Helvetica", 11)
        p.drawString(1 * inch, height - 1.9 * inch, specialization)
        p.drawString(width - 3 * inch, height - 1.9 * inch, f"Date: {new_prescription.verified_at.strftime('%d-%m-%Y %I:%M %p')}") # This will now work

        # Patient Info
        p.line(0.8 * inch, height - 2.1 * inch, width - 0.8 * inch, height - 2.1 * inch)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * inch, height - 2.4 * inch, "Patient Information")
        p.setFont("Helvetica", 11)
        p.drawString(1.1 * inch, height - 2.6 * inch, f"Name: {patient.name}")
        p.drawString(1.1 * inch, height - 2.8 * inch, f"Age: {patient.age or 'N/A'} years")
        p.drawString(3.5 * inch, height - 2.8 * inch, f"Gender: {patient.gender}")
        p.drawString(1.1 * inch, height - 3.0 * inch, f"Blood Group: {patient.blood_group or 'N/A'}")
        p.drawString(3.5 * inch, height - 3.0 * inch, f"Weight: {patient.weight or 'N/A'} kg")
        p.drawString(1.1 * inch, height - 3.2 * inch, f"Blood Pressure: {new_prescription.blood_pressure or 'N/A'}")
        
        # ... (rest of your PDF drawing code remains the same)
        p.line(0.8 * inch, height - 3.4 * inch, width - 0.8 * inch, height - 3.4 * inch)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * inch, height - 3.7 * inch, "Consultation Notes / Diagnosis:")
        text_object = p.beginText(1.1 * inch, height - 4.0 * inch)
        text_object.setFont("Helvetica", 11)
        text_object.setLeading(14)
        notes = new_prescription.transcribed_text or "No notes recorded."
        for line in notes.split('\n'): text_object.textLine(line.strip())
        p.drawText(text_object)
        p.line(width - 3.5 * inch, 1.8 * inch, width - 1 * inch, 1.8 * inch)
        p.setFont("Helvetica-Bold", 11)
        p.drawRightString(width - 1 * inch, 1.6 * inch, "Doctor’s Signature")
        p.setFont("Helvetica-Oblique", 9)
        p.drawCentredString(width / 2.0, 0.8 * inch, "Digitally verified prescription • Imaginex Health System © 2025")

        # Finalize the PDF
        p.showPage()
        p.save()
        pdf_data = buffer.getvalue()
        buffer.close()

        # --- 4. SAVE PDF TO THE MODEL AND REDIRECT ---
        filename = f'prescription_{patient.id}_{new_prescription.id}.pdf'
        new_prescription.prescription_file.save(filename, ContentFile(pdf_data), save=True)
        
        return redirect('prescription')

    # This is for the GET request
    return render(request, "prescription.html", {})



# --- OTHER VIEWS REMAIN THE SAME ---
def home(request): return render(request, "home.html")
@login_required
def history(request):
    all_prescriptions = Prescription.objects.all().order_by('-date_created')
    return render(request, 'history.html', {'prescriptions': all_prescriptions})
def contact(request): return render(request, 'contact.html')
def help(request): return render(request, 'help.html')

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
    try: doctor = request.user.doctor
    except Doctor.DoesNotExist: doctor = None
    return render(request, 'profile.html', {'doctor': doctor})

# Placeholder for SMS
def send_sms(request, prescription_id):
    return JsonResponse({'status': 'info', 'message': 'SMS functionality not fully implemented.'})

