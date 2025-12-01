from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # 1. Lobby
    # Nombre: 'lobby' (como espera tu template lobby.html)
    path('<uuid:access_code>/', views.lobby_view, name='lobby'),
    
    # 2. Tech Check
    # Nombre: 'tech_check'
    path('<uuid:access_code>/check/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),

    # 3. Runner (El examen)
    # Nombre: 'take' (CRÍTICO: así lo llama tu template tech_check.html)
    path('<uuid:access_code>/take/<uuid:attempt_id>/', views.exam_runner_view, name='take'),

    # 4. Guardar respuesta (AJAX)
    path('save/<uuid:attempt_id>/', views.save_answer, name='save_answer'),

    # 5. Finalizar (Nuevas rutas)
    path('submit/<uuid:attempt_id>/', views.submit_exam_view, name='submit_exam'),
    path('finished/<uuid:attempt_id>/', views.exam_finished_view, name='exam_finished'),
]
