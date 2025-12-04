from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # 1. Lobby
    path('<uuid:access_code>/', views.lobby_view, name='lobby'),
    
    # 2. Tech Check (Paso 1: Hardware)
    path('<uuid:access_code>/check/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),

    # 3. Biometric Gate (Paso 2: Identidad - NUEVO)
    path('<uuid:access_code>/gate/<uuid:attempt_id>/', views.biometric_gate_view, name='gate'),
    
    # 4. API Registro Biométrico (NUEVO)
    path('register_biometrics/<uuid:attempt_id>/', views.register_biometrics, name='register_biometrics'),

    # 5. Runner (Examen)
    path('<uuid:access_code>/take/<uuid:attempt_id>/', views.exam_runner_view, name='take'),

    # 6. AJAX / Funcionalidad
    path('save/<uuid:attempt_id>/', views.save_answer, name='save_answer'),
    path('submit/<uuid:attempt_id>/', views.submit_exam_view, name='submit_exam'),
    path('finished/<uuid:attempt_id>/', views.exam_finished_view, name='exam_finished'),
    
    # 7. Seguridad
    path('log/<uuid:attempt_id>/', views.log_event, name='log_event'),
]
