"""
Definiciones de URL principales para plataforma.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

# (S0a) Ruta de Health Check para Render
def health_check(request):
    return HttpResponse("OK: Web Service (S0a) está activo.", content_type="text/plain")

urlpatterns = [
    # (S0a) Panel de Admin del Platform SA
    path('admin/', admin.site.urls),
    
    # (S0a) Health Check
    path('health/', health_check, name='health_check'),

    # (S1b) URLs de Autenticación
    path('accounts/', include('django.contrib.auth.urls')),

    # (S1b) URLs de nuestro Backoffice (Constructor de Exámenes)
    path('backoffice/', include('backoffice.urls')),

    # --- CORRECCIÓN AQUÍ ---
    # Usamos comillas vacías ('') para que no agregue prefijos extra.
    # Así, la ruta '/room/' definida dentro de runner.urls será la que mande.
    path('', include('runner.urls')), 

    # TODO: Redirección de la raíz ('/')
]
