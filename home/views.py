from django.shortcuts import render, redirect
from .models import Patient, Prescription

def home(request):
    """
    Renders the home page.
    """
    return render(request, "home.html")

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
            weight=weight if weight and weight.replace('.','',1).isdigit() else None
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

def history(request):
    """
    Fetches all prescription records from the database to display them.
    """
    all_prescriptions = Prescription.objects.all().order_by('-date_created')
    context = {'prescriptions': all_prescriptions}
    return render(request, 'history.html', context)

def profile(request):
    doctor_data = {
        'name': 'Dr. ABC DEF', 'specialization': 'General Physician',
        'email': 'dr.abc.def@example.com', 'phone': '+91 12345 67890'
    }
    return render(request, 'profile.html', {'doctor': doctor_data})

def contact(request):
    return render(request, 'contact.html')

def help(request):
    return render(request, 'help.html')


