from django.contrib import admin
from .models import Patient, Medicine, Symptom, Prescription

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):  # CORRECTED: Was admin.admin.ModelAdmin
    """
    Customizes the admin interface for the Patient model.
    """
    list_display = ('name', 'age', 'gender', 'phone', 'date_created')
    search_fields = ('name', 'phone')
    list_filter = ('gender', 'date_created')

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
    Customizes the admin interface for the Prescription model.
    """
    list_display = ('patient', 'doctor', 'date_created', 'blood_pressure')
    search_fields = ('patient__name', 'doctor__username')
    list_filter = ('date_created', 'doctor')
    autocomplete_fields = ('patient', 'doctor', 'symptoms', 'medicines')
    fieldsets = (
        (None, {
            'fields': ('patient', 'doctor')
        }),
        ('Consultation Details', {
            'fields': ('blood_pressure', 'transcribed_text')
        }),
        ('Diagnoses & Treatments', {
            'fields': ('symptoms', 'medicines')
        }),
    )

