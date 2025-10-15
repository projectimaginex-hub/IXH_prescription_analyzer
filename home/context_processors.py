# home/context_processors.py

from .models import Doctor

def doctor_profile(request):
    """
    Makes the logged-in user's doctor profile available in all templates.
    """
    if request.user.is_authenticated:
        try:
            # Find the Doctor profile linked to the current user
            doctor = request.user.doctor
            return {'doctor_profile': doctor}
        except Doctor.DoesNotExist:
            # If the user has no doctor profile, return nothing
            return {'doctor_profile': None}
    return {}