from django.urls import path
from . import views  # It's better to import the whole module

urlpatterns = [
    # The root URL of the app points to the home view
    path('', views.home, name='home'),

    # URL for the prescription page
    path('prescription/', views.prescription, name='prescription'),

    # URL for the history page
    path('history/', views.history, name='history'),


    # --- ADD THESE NEW URLS ---
    path('profile/', views.profile, name='profile'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help, name='help'),
<<<<<<< HEAD
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
=======
    
     # --- NEW URL FOR SENDING SMS ---
    # The <int:prescription_id> part is a variable that will hold the ID of the prescription to send
    path('send-sms/<int:prescription_id>/', views.send_sms, name='send-sms'),
>>>>>>> b06d3982be81bd3d4195144fe17aa000fa68a3a6

]
