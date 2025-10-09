from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.utils import timezone

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from .forms import UserForm, DoctorForm
from .models import Patient, Prescription, Doctor

import io


def home(request):
    return render(request, "home.html")


@login_required
def prescription(request):
    if request.method == 'POST':
        patient_name = request.POST.get('patientName')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('bloodGrp')
        weight = request.POST.get('weight')
        blood_pressure = request.POST.get('bp')
        transcribed_text = request.POST.get('transcriptionText')

        # ✅ Validate numeric fields
        age_val = int(age) if age and age.isdigit() else None
        weight_val = float(weight) if weight and weight.replace(
            '.', '', 1).isdigit() else None

        # ✅ Create Patient once
        patient = Patient.objects.create(
            name=patient_name,
            phone=phone,
            age=age_val,
            gender=gender,
            blood_group=blood_group,
            weight=weight_val
        )
        doctor = Doctor.objects.filter(user=request.user).first(
        ) if request.user.is_authenticated else None

        # ✅ Create and save prescription
        new_prescription = Prescription.objects.create(
            patient=patient,
            doctor=doctor,
            blood_pressure=blood_pressure,
            transcribed_text=transcribed_text,
            is_verified=True,
            verified_at=timezone.now()
        )

        # ✅ PDF Generation - Professional Layout
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # ------------------ HEADER ------------------
        p.setFont("Helvetica-Bold", 20)
        p.drawCentredString(width / 2.0, height - 1 * inch,
                            "🏥 IMAGINEX HEALTH CLINIC")

        p.setFont("Helvetica", 11)
        p.drawCentredString(width / 2.0, height - 1.2 * inch,
                            "123 Health Street, Bengaluru, India | +91 98765 43210")
        p.line(0.8 * inch, height - 1.3 * inch,
               width - 0.8 * inch, height - 1.3 * inch)

        # ------------------ DOCTOR INFO ------------------
        doctor_name = f"{new_prescription.doctor.first_name} {
            new_prescription.doctor.last_name}" if new_prescription.doctor else "Dr. ABC DEF"
        specialization = getattr(new_prescription.doctor, "specialization",
                                 "General Physician") if new_prescription.doctor else "General Physician"

        p.setFont("Helvetica-Bold", 13)
        p.drawString(1 * inch, height - 1.7 * inch, doctor_name)
        p.setFont("Helvetica", 11)
        p.drawString(1 * inch, height - 1.9 * inch, specialization)
        p.drawString(width - 2.5 * inch, height - 1.9 * inch,
                     f"Date: {new_prescription.verified_at.strftime('%d-%m-%Y %I:%M %p')}")

        # ------------------ PATIENT INFO ------------------
        p.line(0.8 * inch, height - 2.1 * inch,
               width - 0.8 * inch, height - 2.1 * inch)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * inch, height - 2.4 * inch, "Patient Information")
        p.setFont("Helvetica", 11)
        p.drawString(1.1 * inch, height - 2.6 * inch, f"Name: {patient.name}")
        p.drawString(1.1 * inch, height - 2.8 * inch,
                     f"Age: {patient.age or 'N/A'} years")
        p.drawString(3.2 * inch, height - 2.8 * inch,
                     f"Gender: {patient.gender}")
        p.drawString(1.1 * inch, height - 3.0 * inch,
                     f"Blood Group: {patient.blood_group}")
        p.drawString(3.2 * inch, height - 3.0 * inch,
                     f"Weight: {patient.weight or 'N/A'} kg")
        p.drawString(1.1 * inch, height - 3.2 * inch,
                     f"Blood Pressure: {new_prescription.blood_pressure or 'N/A'}")

        # ------------------ CONSULTATION NOTES ------------------
        p.line(0.8 * inch, height - 3.4 * inch,
               width - 0.8 * inch, height - 3.4 * inch)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * inch, height - 3.7 * inch,
                     "Consultation Notes / Diagnosis:")
        p.setFont("Helvetica", 11)

        text_object = p.beginText(1.1 * inch, height - 4.0 * inch)
        text_object.setLeading(14)  # line spacing
        notes = new_prescription.transcribed_text or "No notes recorded."
        for line in notes.split('\n'):
            text_object.textLine(line.strip())
        p.drawText(text_object)

        # ------------------ SIGNATURE AREA ------------------
        p.line(0.8 * inch, 1.5 * inch, width - 0.8 * inch, 1.5 * inch)
        p.setFont("Helvetica-Bold", 11)
        p.drawString(width - 2.7 * inch, 1.3 * inch, "______________________")
        p.drawString(width - 2.4 * inch, 1.1 * inch, "Doctor’s Signature")

        # ------------------ FOOTER ------------------
        p.setFont("Helvetica-Oblique", 9)
        p.drawCentredString(width / 2.0, 0.8 * inch,
                            "Digitally verified prescription • Imaginex Health System © 2025")

        # Save PDF
        p.showPage()
        p.save()

        pdf = buffer.getvalue()
        buffer.close()

        # Save file to model
        filename = f'prescription_{patient.id}_{
            timezone.now().strftime("%Y%m%d%H%M%S")}.pdf'
        new_prescription.prescription_file.save(filename, ContentFile(pdf))
        return redirect('history')
    return render(request, "prescription.html")


@login_required
def send_sms(request, prescription_id):
    if request.method == 'POST':
        try:
            prescription = Prescription.objects.get(id=prescription_id)
            patient_phone = prescription.patient.phone

            if not patient_phone:
                return JsonResponse({'status': 'error', 'message': 'Patient phone number is not available.'}, status=400)

            # TODO: Implement Twilio logic
            return JsonResponse({'status': 'success', 'message': f"Prescription link would be sent to {patient_phone}."})

        except Prescription.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Prescription not found.'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


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
            Doctor.objects.create(
                user=user,
                first_name=doctor_form.cleaned_data['first_name'],
                last_name=doctor_form.cleaned_data['last_name'],
                specialization=doctor_form.cleaned_data['specialization'],
                phone=doctor_form.cleaned_data['phone'],
                email=user.email
            )
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
    doctor = Doctor.objects.filter(user=request.user).first()
    return render(request, 'profile.html', {'doctor': doctor})
