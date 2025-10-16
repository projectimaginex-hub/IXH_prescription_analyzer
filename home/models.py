from django.db import models
from django.contrib.auth.models import User


class Patient(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True, null=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Medicine(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Symptom(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Audio(models.Model):
    """
    --- NEW MODEL BASED ON YOUR NOTES ---
    Stores the audio recording and its transcription for a consultation.
    """
    audio_file = models.FileField(upload_to='consultation_audio/')
    transcribed_text = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    
    
class Doctor(models.Model):
    """Stores the professional profile for a doctor."""
    # --- One-to-One Relationship ---
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    specialization = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    experience = models.PositiveIntegerField(null=True, blank=True, help_text="Years of experience")
    profile_picture = models.ImageField(upload_to='doctor_pics/', blank=True, null=True)
    
    # --- NEW FIELDS BASED ON YOUR NOTES ---
    about = models.TextField(blank=True, help_text="A short bio for the profile page.")
    professional_details = models.TextField(blank=True, help_text="Degrees, certifications, etc.")
    signature = models.ImageField(upload_to='doctor_signatures/', blank=True, null=True)

    def __str__(self):
        return f"Dr. {self.first_name} {self.last_name}"


class Prescription(models.Model):
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='prescriptions')
    doctor = models.ForeignKey(
        Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    
    # --- UPDATED: Many-to-One Relationship with the new Audio model ---
    # A prescription can have multiple audio recordings associated with it over time,
    # but based on your diagram, we will link one audio recording to one prescription.
    # If the audio record is deleted, this field becomes NULL.
    audio = models.ForeignKey(Audio, on_delete=models.SET_NULL, null=True, blank=True)
    
    # --- Many-to-Many Relationships ---
    symptoms = models.ManyToManyField(Symptom, blank=True)
    medicines = models.ManyToManyField(Medicine, blank=True)
    
    blood_pressure = models.CharField(max_length=20, blank=True)
    transcribed_text = models.TextField(blank=True)
    prescription_file = models.FileField(upload_to='prescriptions/', blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)

    # --- NEW FIELDS FOR E-SIGNATURE ---
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    
     # --- NEW FIELDS FOR STORING FILES LOCALLY ---
    audio_recording = models.FileField(upload_to='audio_recordings/', blank=True, null=True)
    transcript_file = models.FileField(upload_to='transcripts/', blank=True, null=True)


    def __str__(self):
        return f"Prescription for {self.patient.name} on {self.date_created.strftime('%Y-%m-%d')}"
