import io
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.files.base import ContentFile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from .models import Patient, Prescription

def home(request):
    return render(request, "home.html")

def prescription(request):
    if request.method == 'POST':
        # 1. Get Patient data
        patient_name = request.POST.get('patientName')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('bloodGrp')
        weight = request.POST.get('weight')
        blood_pressure = request.POST.get('bp')
        transcribed_text = request.POST.get('transcriptionText')

        # 2. More robust validation for numeric fields
        # This ensures empty strings are converted to None (NULL in DB)
        age_val = None
        try:
            if age: age_val = int(age)
        except (ValueError, TypeError):
            pass # Keep age_val as None if conversion fails

        weight_val = None
        try:
            # Check for empty string explicitly
            if weight: weight_val = float(weight)
        except (ValueError, TypeError):
            pass # Keep weight_val as None if conversion fails
        
        # 3. Create and save the Patient object
        patient = Patient.objects.create(
            name=patient_name,
            phone=phone,
            age=age_val,
            gender=gender,
            blood_group=blood_group,
            weight=weight_val
        )

        # 4. Create and SAVE the prescription object FIRST
        new_prescription = Prescription.objects.create(
            patient=patient,
            doctor=request.user if request.user.is_authenticated else None,
            blood_pressure=blood_pressure,
            transcribed_text=transcribed_text
        )

        # --- PDF Generation ---
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(1 * inch, 10.5 * inch, "Medical Prescription")
        p.setFont("Helvetica", 12)
        p.drawString(1 * inch, 10.2 * inch, f"Doctor: {new_prescription.doctor.get_full_name() if new_prescription.doctor else 'Dr. ABC DEF'}")
        p.drawString(1 * inch, 10.0 * inch, f"Date: {new_prescription.date_created.strftime('%Y-%m-%d %H:%M')}")
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
        text = p.beginText(1.2 * inch, 8.3 * inch)
        text.setFont("Helvetica", 11)
        text.setLeading(14)
        notes = new_prescription.transcribed_text or "No transcribed notes available."
        for line in notes.split('\n'):
            text.textLine(line)
        p.drawText(text)
        p.showPage()
        p.save()
        
        pdf = buffer.getvalue()
        buffer.close()

        # 5. Save the PDF to the model
        filename = f'prescription_{patient.id}_{new_prescription.id}.pdf'
        new_prescription.prescription_file.save(filename, ContentFile(pdf), save=True)

        # 6. Prepare and return the HTTP response for download
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, "prescription.html", {})

def history(request):
    all_prescriptions = Prescription.objects.all().order_by('-date_created')
    return render(request, 'history.html', {'prescriptions': all_prescriptions})

def profile(request):
    doctor_data = {'name': 'Dr. ABC DEF', 'specialization': 'General Physician', 'email': 'dr.abc.def@example.com', 'phone': '+91 12345 67890'}
    return render(request, 'profile.html', {'doctor': doctor_data})

def contact(request):
    return render(request, 'contact.html')

def help(request):
    return render(request, 'help.html')
