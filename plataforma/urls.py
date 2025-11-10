"""
Definición de URLs para plataforma.
Sprint S0a: Setup de Arquitectura Core
"""
from django.contrib import admin
from django.urls import path
from django.http import HttpResponse

def health_check(request):
    """Chequeo de salud simple para Render (Spec C4-4)."""
    return HttpResponse("OK: Web Service (S0a) está activo.")

urlpatterns = [
    # Panel de Admin de Django (lo usará el Platform SA en S0b)
    path('admin/', admin.site.urls),
    
    # Endpoint de salud para Render
    path('health/', health_check), 
]
