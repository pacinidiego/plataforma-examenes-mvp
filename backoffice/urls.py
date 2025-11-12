from django.urls import path
from . import views

# (S1b) Rutas para el Backoffice del Docente
urlpatterns = [
    # La URL /backoffice/
    path('', views.dashboard, name='backoffice_dashboard'),
]
