from .models import Patient, Prescription, Medicine, Symptom
from django.contrib import admin

from .models import Doctor, Patient, Medicine, Symptom, Prescription, Audio


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    # --- UPDATED: Added new fields to the display ---
    list_display = ('first_name', 'last_name', 'specialization', 'phone', 'email')
    search_fields = ('first_name', 'last_name', 'email')
    fieldsets = (
        ("Professional Info", {
            "fields": ('user', 'first_name', 'last_name', 'specialization', 'experience')
        }),
        # --- UPDATED: Added new fields to a new fieldset ---
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
    list_display = ('name', 'age', 'gender', 'phone', 'date_created')
    search_fields = ('name', 'phone')
    list_filter = ('gender', 'date_created')
    readonly_fields = ('date_created',)
    list_display = ('name', 'email', 'age', 'gender', 'phone', 'date_created') # <-- ADD 'email'
    search_fields = ('name', 'phone', 'email') # <-- ADD 'email'


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Medicine model.
    """
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Symptom model.
    """
    search_fields = ('name',)

# --- NEW: Register the Audio model with the admin site ---
@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    list_display = ('id', 'date_created')
    readonly_fields = ('date_created',)
    search_fields = ('id', 'transcribed_text')

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    """
    Customizes the admin interface for the Prescription model to show related Patient data.
    """

    # --- Functions to get related Patient attributes for display ---
    def get_patient_name(self, obj):
        return obj.patient.name
    get_patient_name.short_description = 'Patient Name'

    def get_patient_phone(self, obj):
        return obj.patient.phone
    get_patient_phone.short_description = 'Patient Phone'

    def get_patient_age(self, obj):
        return obj.patient.age
    get_patient_age.short_description = 'Patient Age'

    def get_patient_gender(self, obj):
        return obj.patient.gender
    get_patient_gender.short_description = 'Gender'

    def get_patient_weight(self, obj):
        return obj.patient.weight
    get_patient_weight.short_description = 'Weight (kg)'

    def get_patient_blood_group(self, obj):
        return obj.patient.blood_group
    get_patient_blood_group.short_description = 'Blood Group'

    def get_blood_pressure(self, obj):
        return obj.blood_pressure
    get_blood_pressure.short_description = 'BP'

    def get_symptoms_analysed(self, obj):
        # Joins the names of all related symptoms into a single string
        return ", ".join([s.name for s in obj.symptoms.all()])
    get_symptoms_analysed.short_description = 'Symptoms Analysed'

    # --- UPDATED: 'list_display' now shows all the requested data ---
    list_display = (
        'id',
        'get_patient_name',
        'get_patient_age',
        'get_patient_gender',
        'get_patient_weight',
        'get_patient_blood_group',
        'get_blood_pressure',
        'get_symptoms_analysed',
        'date_created',
        'is_verified',
    )

    # --- The rest of the configuration remains the same ---
    list_display = ('id', 'patient', 'doctor', 'date_created', 'is_verified')
    search_fields = ('patient__name', 'doctor__first_name')
    list_filter = ('date_created', 'is_verified', 'doctor')
    autocomplete_fields = ('patient', 'doctor', 'symptoms', 'medicines', 'audio')
    readonly_fields = ('date_created', 'verified_at')

    fieldsets = (
        ('Primary Information', {
            'fields': ('patient', 'doctor', 'date_created')
        }),
        
        ('Verification Details', {
            'fields': ('is_verified', 'verified_at', 'prescription_file')
        }),
    # --- UPDATED: Added the new audio link ---
        ('Consultation Details', {
            'fields': ('blood_pressure', 'symptoms', 'medicines', 'audio')
        }),
       
    )


