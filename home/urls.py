from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('prescription/', views.prescription, name='prescription'),
    path('history/', views.history, name='history'),
    # New URL for the prescription detail page
    path('history/<int:prescription_id>/', views.prescription_detail, name='prescription_detail'),
    path('profile/', views.profile, name='profile'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help, name='help'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('send-sms/<int:prescription_id>/', views.send_sms, name='send-sms'),
    path('transcribe-audio/', views.transcribe_audio, name='transcribe-audio'),
]


