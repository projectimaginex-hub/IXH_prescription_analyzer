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
