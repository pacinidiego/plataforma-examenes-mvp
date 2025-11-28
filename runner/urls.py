from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # 1. Lobby (Entrada)
    path('<uuid:access_code>/', views.lobby_view, name='lobby'),
    
    # 2. Tech Check (NUEVO: Paso intermedio)
    # Necesitamos el attempt_id para saber quién es el que está probando la cámara
    path('<uuid:access_code>/check/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),

    # 3. Runner (El examen real)
    # Ahora también recibe attempt_id para saber qué intento retomar
    path('<uuid:access_code>/take/<uuid:attempt_id>/', views.exam_runner_view, name='take'),
]
