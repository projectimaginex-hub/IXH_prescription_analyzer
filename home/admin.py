from .models import Patient, Prescription, Medicine, Symptom
from django.contrib import admin

from .models import Doctor, Patient, Medicine, Symptom, Prescription


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'specialization',
                    'phone', 'email', 'experience')
    search_fields = ('first_name', 'specialization', 'email')
    list_filter = ('specialization',)
    ordering = ('first_name',)
    fieldsets = (
        ("Doctor Info", {
            "fields": ('user', 'first_name', 'specialization', 'experience')
        }),
        ("Contact Details", {
            "fields": ('email', 'phone', 'profile_picture')
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
    search_fields = ('patient__name', 'doctor__username', 'symptoms__name')
    list_filter = ('date_created', 'is_verified', 'doctor')
    autocomplete_fields = ('patient', 'doctor', 'symptoms', 'medicines')

    readonly_fields = ('date_created', 'verified_at')

    fieldsets = (
        ('Primary Information', {
            'fields': ('patient', 'doctor', 'date_created')
        }),
        ('Verification Details', {
            'fields': ('is_verified', 'verified_at', 'prescription_file')
        }),
        ('Consultation Details', {
            'fields': ('blood_pressure', 'transcribed_text')
        }),
        ('Diagnoses & Treatments', {
            'fields': ('symptoms', 'medicines')
        }),
    )


