<<<<<<< HEAD
from .forms import UserForm, DoctorForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.shortcuts import render, redirect
from .models import Patient, Prescription, Doctor

=======
import io
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.core.files.base import ContentFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from .models import Patient, Prescription
# Note: Twilio integration would require configuration in settings.py
# from twilio.rest import Client
>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6

def home(request):
    return render(request, "home.html")


@login_required
def prescription(request):
    if request.method == 'POST':
        # This view now handles the "Verify" button submission
        patient_name = request.POST.get('patientName')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('bloodGrp')
        weight = request.POST.get('weight')
<<<<<<< HEAD

        patient = Patient.objects.create(
            name=patient_name,
            phone=phone,
            age=age if age and age.isdigit() else None,
            gender=gender,
            blood_group=blood_group,
            weight=weight if weight and weight.replace(
                '.', '', 1).isdigit() else None
        )

=======
>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6
        blood_pressure = request.POST.get('bp')
        transcribed_text = request.POST.get('transcriptionText')

        # Robust validation
        age_val = int(age) if age and age.isdigit() else None
        weight_val = float(weight) if weight and weight.replace('.','',1).isdigit() else None
        
        patient = Patient.objects.create(
            name=patient_name, phone=phone, age=age_val,
            gender=gender, blood_group=blood_group, weight=weight_val
        )

        # Create the prescription object but DON'T save it yet
        new_prescription = Prescription(
            patient=patient,
            doctor=request.user if request.user.is_authenticated else None,
            blood_pressure=blood_pressure,
            transcribed_text=transcribed_text,
            is_verified=True,          # Set the verification flag
            verified_at=timezone.now() # Record the verification time
        )
<<<<<<< HEAD

        return redirect('history')
=======
>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6

        # --- PDF Generation ---
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(1 * inch, 10.5 * inch, "Medical Prescription")
        p.setFont("Helvetica", 12)
        p.drawString(1 * inch, 10.2 * inch, f"Doctor: {new_prescription.doctor.get_full_name() if new_prescription.doctor else 'Dr. ABC DEF'}")
        p.drawString(1 * inch, 10.0 * inch, f"Date: {new_prescription.verified_at.strftime('%Y-%m-%d %H:%M')}")
        p.line(1 * inch, 9.9 * inch, 7.5 * inch, 9.9 * inch)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * inch, 9.6 * inch, "Patient Information")
        p.setFont("Helvetica", 12)
        p.drawString(1.2 * inch, 9.4 * inch, f"Name: {patient.name}")
        p.drawString(1.2 * inch, 9.2 * inch, f"Age: {patient.age if patient.age is not None else 'N/A'}")
        p.drawString(1.2 * inch, 9.0 * inch, f"Gender: {patient.gender}")
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * inch, 8.5 * inch, "Consultation Notes")
        p.setFont("Helvetica", 12)
        text_object = p.beginText(1.2 * inch, 8.3 * inch)
        notes = new_prescription.transcribed_text or "No transcribed notes."
        for line in notes.split('\n'):
            text_object.textLine(line)
        p.drawText(text_object)
        p.showPage()
        p.save()
        
        pdf = buffer.getvalue()
        buffer.close()

        # Save the generated PDF to the model instance
        filename = f'prescription_{patient.id}_{timezone.now().strftime("%Y%m%d%H%M%S")}.pdf'
        new_prescription.prescription_file.save(filename, ContentFile(pdf))
        # The model is saved here for the first and only time

        return redirect('prescription')

    return render(request, "prescription.html", {})

<<<<<<< HEAD

@login_required
=======
def send_sms(request, prescription_id):
    # This is a placeholder for the "Send" button functionality
    if request.method == 'POST':
        try:
            prescription = Prescription.objects.get(id=prescription_id)
            patient_phone = prescription.patient.phone
            
            if not patient_phone:
                return JsonResponse({'status': 'error', 'message': 'Patient phone number is not available.'}, status=400)
                
            # --- TWILIO LOGIC WOULD GO HERE ---
            # account_sid = 'YOUR_TWILIO_ACCOUNT_SID'
            # auth_token = 'YOUR_TWILIO_AUTH_TOKEN'
            # client = Client(account_sid, auth_token)
            # message = client.messages.create(
            #     body=f"Hello {prescription.patient.name}, your prescription is ready. View it here: {request.build_absolute_uri(prescription.prescription_file.url)}",
            #     from_='YOUR_TWILIO_PHONE_NUMBER',
            #     to=patient_phone
            # )
            # print(f"SMS Sent! SID: {message.sid}")
            # --- END TWILIO LOGIC ---

            # For now, we'll just simulate success
            return JsonResponse({'status': 'success', 'message': f"Prescription link would be sent to {patient_phone}."})

        except Prescription.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Prescription not found.'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6
def history(request):
    all_prescriptions = Prescription.objects.all().order_by('-date_created')
    return render(request, 'history.html', {'prescriptions': all_prescriptions})

<<<<<<< HEAD
=======
def profile(request):
    doctor_data = {'name': 'Dr. ABC DEF', 'specialization': 'General Physician', 'email': 'dr.abc.def@example.com', 'phone': '+91 12345 67890'}
    return render(request, 'profile.html', {'doctor': doctor_data})
>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6

def contact(request):
    return render(request, 'contact.html')


def help(request):
    return render(request, 'help.html')

<<<<<<< HEAD

def signup_view(request):
    if request.method == 'POST':
        user_form = UserForm(request.POST)
        doctor_form = DoctorForm(request.POST)
        if user_form.is_valid() and doctor_form.is_valid():
            user = user_form.save(commit=False)
            user.set_password(user_form.cleaned_data['password'])
            user.save()
            # Create doctor object linked to the user
            Doctor.objects.create(
                user=user,
                first_name=doctor_form.cleaned_data['first_name'],
                last_name=doctor_form.cleaned_data['last_name'],
                specialization=doctor_form.cleaned_data['specialization'],
                phone=doctor_form.cleaned_data['phone'],
                email=user.email
            )
            # Optionally login the user
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
            user = form.get_user()
            login(request, user)
            return redirect('profile')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile(request):
    doctor = Doctor.objects.filter(user=request.user).first()
    print(doctor)
    return render(request, 'profile.html', {'doctor': doctor})
=======
>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6
