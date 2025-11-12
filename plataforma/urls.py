"""
Definiciones de URL principales para plataforma.
"""
from django.contrib import admin
from django.urls import path, include # ¡Asegúrate de que 'include' esté importado!
from django.http import HttpResponse

# (S0a) Ruta de Health Check para Render
def health_check(request):
    return HttpResponse("OK: Web Service (S0a) está activo.", content_type="text/plain")

urlpatterns = [
    # (S0a) Panel de Admin del Platform SA
    path('admin/', admin.site.urls),
    
    # (S0a) Health Check
    path('health/', health_check, name='health_check'),

    # (S1b) URLs de Autenticación de Django (login, logout, etc.)
    # Esto nos da la página /accounts/login/
    path('accounts/', include('django.contrib.auth.urls')),

    # (S1b) URLs de nuestro Backoffice (Constructor de Exámenes)
    # Todo lo que esté en /backoffice/ lo manejará nuestra nueva app
    path('backoffice/', include('backoffice.urls')),

    # TODO: Redirección de la raíz ('/') al backoffice si está logueado,
    # o al login si no lo está.
]
