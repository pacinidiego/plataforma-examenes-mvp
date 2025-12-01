from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # 1. Lobby (Volvemos a name='lobby' para que coincida con tus templates)
    path('<uuid:access_code>/', views.lobby_view, name='lobby'),
    
    # 2. Tech Check
    path('<uuid:access_code>/check/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),

    # 3. Runner (El examen real)
    path('<uuid:access_code>/take/<uuid:attempt_id>/', views.exam_runner_view, name='exam_runner'),

    # 4. Guardar respuesta (AJAX/Fetch)
    path('save/<uuid:attempt_id>/', views.save_answer, name='save_answer'),

    # === RUTAS NUEVAS ===
    path('submit/<uuid:attempt_id>/', views.submit_exam_view, name='submit_exam'),
    path('finished/<uuid:attempt_id>/', views.exam_finished_view, name='exam_finished'),
]
