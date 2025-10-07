from django.shortcuts import render


def home(request):

    patient = {
        "name": "John Doe",
        "phone": "9876543210",
        "age": 35,
        "gender": "Male",
        "bloodGrp": "O+",
        "weight": 70,
        "bp": "120/80"
    }
    return render(request, "home.html", {"patient": patient})


def prescription(request):
    return render(request, "prescription.html")

def history(request):
    return render(request, 'history.html')

def profile(request):
    # You can pass doctor's data from a database here in the future
    doctor_data = {
        'name': 'Dr. ABC DEF',
        'specialization': 'General Physician',
        'email': 'dr.abc.def@example.com',
        'phone': '+91 12345 67890'
    }
    return render(request, 'profile.html', {'doctor': doctor_data})

def contact(request):
    return render(request, 'contact.html')

def help(request):
    return render(request, 'help.html')


