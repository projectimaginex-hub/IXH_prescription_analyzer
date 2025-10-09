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
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

]
