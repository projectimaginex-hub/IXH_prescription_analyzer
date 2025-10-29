from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('prescription/', views.prescription, name='prescription'),
    path('history/', views.history, name='history'),
    path('history/<int:prescription_id>/',
         views.prescription_detail, name='prescription_detail'),
    path('profile/', views.profile, name='profile'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help, name='help'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('send-email/<int:prescription_id>/',
         views.send_email, name='send-email'),  # <-- ADD THIS
    path('profile/edit/', views.edit_profile, name='edit-profile'),
    path('get_previous_medication/', views.get_previous_medication,
         name='get_previous_medication'),
    path('transcribe-audio/', views.transcribe_audio, name='transcribe-audio'),
    path('update_medication', views.update_medication, name='update_medication'),
]
