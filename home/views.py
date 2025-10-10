from .forms import UserForm, DoctorForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.shortcuts import render, redirect
from .models import Patient, Prescription, Doctor


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

        patient = Patient.objects.create(
            name=patient_name,
            phone=phone,
            age=age if age and age.isdigit() else None,
            gender=gender,
            blood_group=blood_group,
            weight=weight if weight and weight.replace(
                '.', '', 1).isdigit() else None
        )

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

        return redirect('history')

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
