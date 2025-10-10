import io
import time
import requests # New import
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.core.files.base import ContentFile
from django.conf import settings # New import
from django.views.decorators.csrf import csrf_exempt # New import
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
@csrf_exempt # Use this decorator for API-like views that receive data from JS
def transcribe_audio(request):
    if request.method == 'POST':
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return JsonResponse({'status': 'error', 'message': 'No audio file received.'}, status=400)

        headers = {'authorization': settings.ASSEMBLYAI_API_KEY}

        # 1. Upload the audio file to AssemblyAI
        try:
            upload_response = requests.post(
                ASSEMBLYAI_UPLOAD_ENDPOINT,
                headers=headers,
                data=audio_file.read()
            )
            upload_response.raise_for_status()
            upload_url = upload_response.json()['upload_url']
        except requests.RequestException as e:
            return JsonResponse({'status': 'error', 'message': f'Failed to upload audio: {e}'}, status=500)

        # 2. Request transcription from AssemblyAI
        json_data = {'audio_url': upload_url}
        try:
            transcript_response = requests.post(
                ASSEMBLYAI_TRANSCRIPT_ENDPOINT,
                json=json_data,
                headers=headers
            )
            transcript_response.raise_for_status()
            transcript_id = transcript_response.json()['id']
        except requests.RequestException as e:
            return JsonResponse({'status': 'error', 'message': f'Failed to request transcript: {e}'}, status=500)

        # 3. Poll for the transcription result
        polling_endpoint = f"{ASSEMBLYAI_TRANSCRIPT_ENDPOINT}/{transcript_id}"
        while True:
            try:
                polling_response = requests.get(polling_endpoint, headers=headers)
                polling_response.raise_for_status()
                polling_result = polling_response.json()

                if polling_result['status'] == 'completed':
                    return JsonResponse({'status': 'success', 'text': polling_result['text']})
                elif polling_result['status'] == 'error':
                    return JsonResponse({'status': 'error', 'message': polling_result['error']}, status=500)
                
                # Wait for 3 seconds before polling again
                time.sleep(3)
            except requests.RequestException as e:
                return JsonResponse({'status': 'error', 'message': f'Polling failed: {e}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


# --- YOUR EXISTING VIEWS (prescription, history, etc.) ---
# ... (all your other views like home, prescription, history, login, signup, etc. remain here) ...
# I am including them for completeness.

@login_required
def prescription(request):
    if request.method == 'POST':
        # ... (Your existing prescription saving logic)
        patient_name = request.POST.get('patientName')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('bloodGrp')
        weight = request.POST.get('weight')
        blood_pressure = request.POST.get('bp')
        transcribed_text = request.POST.get('transcriptionText')

        age_val = int(age) if age and age.isdigit() else None
        weight_val = float(weight) if weight and weight.replace('.','',1).isdigit() else None
        
        patient = Patient.objects.create(
            name=patient_name, phone=phone, age=age_val,
            gender=gender, blood_group=blood_group, weight=weight_val
        )

        try:
            doctor = request.user.doctor
        except Doctor.DoesNotExist:
            doctor = None

        new_prescription = Prescription.objects.create(
            patient=patient,
            doctor=doctor,
            blood_pressure=blood_pressure,
            transcribed_text=transcribed_text,
            is_verified=True,
            verified_at=timezone.now()
        )

        # --- PDF Generation ---
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        # (Your PDF drawing code here)
        p.showPage()
        p.save()
        pdf = buffer.getvalue()
        buffer.close()
        
        filename = f'prescription_{patient.id}_{timezone.now().strftime("%Y%m%d%H%M%S")}.pdf'
        new_prescription.prescription_file.save(filename, ContentFile(pdf))
        
        return redirect('prescription')

    return render(request, "prescription.html", {})

def home(request):
    return render(request, "home.html")

@login_required
def history(request):
    all_prescriptions = Prescription.objects.all().order_by('-date_created')
    return render(request, 'history.html', {'prescriptions': all_prescriptions})

def contact(request):
    return render(request, 'contact.html')

def help(request):
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
        user_form = UserForm()
        doctor_form = DoctorForm()
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
def send_sms(request, prescription_id):
    return JsonResponse({'status': 'info', 'message': 'SMS functionality not fully implemented.'})

