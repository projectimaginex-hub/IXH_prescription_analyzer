from django import forms
from django.contrib.auth.models import User
from .models import Doctor , ContactSubmission


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']


class DoctorForm(forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ['first_name', 'last_name', 'specialization', 'phone',
                  'email', 'experience', 'profile_picture']

class DoctorProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ['first_name', 'last_name', 'specialization', 
                  'phone', 'email', 'experience', 'profile_picture']

# --- NEW FORM FOR CONTACT PAGE VALIDATION ---
class ContactForm(forms.ModelForm):
    """
    Form for the contact page, linked to the ContactSubmission model.
    Django will automatically handle validation based on the model's fields.
    """
    class Meta:
        model = ContactSubmission
        fields = ['name', 'email', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'required': True}),
            'email': forms.EmailInput(attrs={'required': True}),
            'subject': forms.TextInput(attrs={'required': True}),
            'message': forms.Textarea(attrs={'rows': 5, 'required': True}),
        }