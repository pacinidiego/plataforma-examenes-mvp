"""
Definiciones de URL principales para plataforma.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
import os
import time

START_TIME = time.time()

@require_GET
def health_check(request):
    if request.headers.get('X-X71-Key') != os.environ.get('X71_API_KEY'):
        return JsonResponse({"error": "forbidden"}, status=403)

    db_ok = True
    try:
        from django.db import connection
        connection.ensure_connection()
    except Exception:
        db_ok = False

    return JsonResponse({
        "status": "ok",
        "app": "plataforma-examenes",
        "version": "1.0.0",
        "db": db_ok,
        "uptime_seconds": int(time.time() - START_TIME),
    })

def robots_txt(request):
    content = "User-agent: *\nDisallow: /\n"
    return HttpResponse(content, content_type="text/plain")

urlpatterns = [
    # (S0a) Panel de Admin del Platform SA
    path('admin/', admin.site.urls),
    
    # (S0a) Health Check
    path('health/', health_check, name='health_check'),

    # Robots
    path('robots.txt', robots_txt, name='robots_txt'),

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
