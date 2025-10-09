from .forms import UserForm, DoctorForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.shortcuts import render, redirect
from .models import Patient, Prescription, Doctor


def home(request):
    """
    Renders the home page.
    """
    return render(request, "home.html")


@login_required
def prescription(request):
    """
    Handles both displaying the prescription form (GET) and saving the
    submitted prescription data to the database (POST).
    """
    if request.method == 'POST':
        # --- This block runs when the form is submitted ---
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

        Prescription.objects.create(
            patient=patient,
            doctor=request.user if request.user.is_authenticated else None,
            blood_pressure=blood_pressure,
            transcribed_text=transcribed_text
        )

        return redirect('history')

    # --- This block runs for GET requests (initial page load) ---
    return render(request, "prescription.html", {})


@login_required
def history(request):
    """
    Fetches all prescription records from the database to display them.
    """
    all_prescriptions = Prescription.objects.all().order_by('-date_created')
    context = {'prescriptions': all_prescriptions}
    return render(request, 'history.html', context)


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
