from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # 1. Lobby (Entrada)
    # Cambié name='lobby' a 'lobby_view' para que funcione el botón "Volver" de la pantalla final
    path('<uuid:access_code>/', views.lobby_view, name='lobby_view'),
    
    # 2. Tech Check
    path('<uuid:access_code>/check/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),

    # 3. Runner (El examen real)
    path('<uuid:access_code>/take/<uuid:attempt_id>/', views.exam_runner_view, name='exam_runner'),

    # 4. Guardar respuesta (AJAX/Fetch)
    path('save/<uuid:attempt_id>/', views.save_answer, name='save_answer'),

    # === RUTAS NUEVAS (CRÍTICAS PARA FINALIZAR) ===
    # Esta es la que busca el botón "Entregar"
    path('submit/<uuid:attempt_id>/', views.submit_exam_view, name='submit_exam'),
    
    # Esta es la pantalla de "Gracias / Nota final"
    path('finished/<uuid:attempt_id>/', views.exam_finished_view, name='exam_finished'),
]
