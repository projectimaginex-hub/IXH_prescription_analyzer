from django.urls import path
from .views import home, prescription

urlpatterns = [
    path('Home', home, name='home'),
    path('', home, name='home'),
    path('prescription', prescription, name='prescription')
]
