from .models import Patient, Prescription, Medicine, Symptom
from django.contrib import admin

from .models import Doctor, Patient, Medicine, Symptom, Prescription, Audio , ContactSubmission,LLMAudit,MedicalHistory


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    # --- UPDATED: Added new fields to the display ---
    list_display = ('first_name', 'last_name', 'specialization', 'clinic_name', 'phone', 'email')
    search_fields = ('first_name', 'last_name', 'email', 'clinic_name')
    fieldsets = (
        ("Professional Info", {
            "fields": ('user', 'first_name', 'last_name', 'specialization', 'experience')
        }),
        # --- UPDATED: ADDED CLINIC DETAILS TO FIELDSET ---
        ("Clinic Details (Branding)", {
            "fields": ('clinic_name', 'clinic_address', 'clinic_logo')
        }),
        ("Profile Details", {
            "fields": ('about', 'professional_details', 'profile_picture', 'signature')
        }),
        ("Contact Details", {
            "fields": ('email', 'phone')
        }),
    )


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Patient model.
    """
    list_display = ('name', 'email', 'age', 'gender', 'phone', 'date_created') 
    search_fields = ('name', 'phone', 'email') 
    list_filter = ('gender', 'date_created')
    readonly_fields = ('date_created',)


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Medicine model.
    """
    list_display = ('name', 'description')
    search_fields = ('name',)


# --- UPDATED ADMIN CLASS FOR SYMPTOM ---
@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Symptom model to show related patients.
    """
    
    def get_patients_with_symptom(self, obj):
        """
        Retrieves the name and ID of patients associated with this symptom via Prescriptions.
        """
        # Traverse the M2M relationship (Symptom -> Prescription -> Patient)
        patients = Patient.objects.filter(prescriptions__symptoms=obj).distinct()
        
        # Format the output as a list of "Name (ID)" strings
        patient_list = [f"{p.name} ({p.id})" for p in patients]
        
        # Display the first few patients, up to 3, joined by commas.
        # Use short_description to ensure HTML is rendered correctly if needed.
        return ", ".join(patient_list[:3]) + (f", ... ({len(patient_list) - 3} more)" if len(patient_list) > 3 else "")

    get_patients_with_symptom.short_description = 'Associated Patients (Name & ID)'
    
    list_display = ('name', 'get_patients_with_symptom')
    search_fields = ('name',)
    
    # Enable searching by patient name via the Prescription intermediate model
    # Note: Direct search by patient ID/Name in this column is complex and often requires a custom Form,
    # but the patient names will be visible in the list.
    list_filter = ('prescription__date_created',)


@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    list_display = ('id', 'date_created')
    readonly_fields = ('date_created',)
    search_fields = ('id', 'transcribed_text')

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for Prescriptions with detailed columns.
    """

    # --- Functions to get related Patient attributes for display ---
    def get_patient_name(self, obj):
        return obj.patient.name
    get_patient_name.short_description = 'Patient Name'
    get_patient_name.admin_order_field = 'patient__name'

    def get_patient_age(self, obj):
        return obj.patient.age
    get_patient_age.short_description = 'Age'

    def get_patient_gender(self, obj):
        return obj.patient.gender
    get_patient_gender.short_description = 'Gender'

    def get_patient_weight(self, obj):
        return obj.patient.weight
    get_patient_weight.short_description = 'Weight (kg)'
    
    def get_symptoms(self, obj):
        return ", ".join([s.name for s in obj.symptoms.all()])
    get_symptoms.short_description = 'Symptoms'

    def get_medicines(self, obj):
        return ", ".join([m.name for m in obj.medicines.all()])
    get_medicines.short_description = 'Medicines'

    list_display = (
        'id',
        'get_patient_name',
        'doctor',
        'get_patient_age',
        'get_patient_gender',
        'get_patient_weight',
        'blood_pressure',
        'get_symptoms',
        'get_medicines',
        'date_created',
        'is_verified',
    )

    search_fields = ('patient__name', 'doctor__first_name', 'symptoms__name', 'medicines__name')
    list_filter = ('date_created', 'is_verified', 'doctor')
    autocomplete_fields = ('patient', 'doctor', 'symptoms', 'medicines', 'audio')
    readonly_fields = ('date_created', 'verified_at')
    fieldsets = (
        ('Primary Information', {'fields': ('patient', 'doctor', 'date_created')}),
        ('Consultation Details', {'fields': ('blood_pressure', 'symptoms', 'medicines', 'audio')}),
        ('Verification & Files', {'fields': ('is_verified', 'verified_at', 'prescription_file')}),
    )


# --- NEW ADMIN CLASS FOR CONTACT MESSAGES ---
@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for contact form submissions.
    """
    list_display = ('name', 'email', 'subject', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    list_filter = ('created_at',)
    # Make all fields read-only, as you should not edit user messages
    readonly_fields = ('name', 'email', 'subject', 'message', 'created_at')

@admin.register(LLMAudit)
class LLMAuditAdmin(admin.ModelAdmin):
    list_display = ('prescription', 'model_name', 'created_at')
    search_fields = ('prescription__id', 'model_name')
    list_filter = ('model_name', 'created_at')
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {
            'fields': ('prescription', 'model_name', 'created_at')
        }),
        ('Audit Log', {
            'fields': ('prompt', 'response')
        }),
    )
    
    
    # --- NEW OCR HISTORY ADMIN ---
@admin.register(MedicalHistory)
class MedicalHistoryAdmin(admin.ModelAdmin):
    """
    Admin view for the scanned medical history (OCR data).
    """
    list_display = ('patient', 'date_scanned', 'get_summary_snippet')
    search_fields = ('patient__name', 'summary_text')
    list_filter = ('date_scanned',)
    readonly_fields = ('date_scanned', 'extracted_json') # JSON is read-only to prevent format errors

    def get_summary_snippet(self, obj):
        return obj.summary_text[:100] + "..." if obj.summary_text else "No summary"
    get_summary_snippet.short_description = 'Extracted Summary'