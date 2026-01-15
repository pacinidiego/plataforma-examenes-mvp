from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # 1. RUTAS FIJAS
    path('api/validate-dni/<uuid:attempt_id>/', views.validate_dni_ocr, name='validate_dni'),
    path('portal/', views.portal_docente_view, name='portal_docente'),
    path('teacher/', views.teacher_home_view, name='teacher_home'),

    # 2. RUTAS DINÁMICAS
    path('room/<str:access_code>/', views.lobby_view, name='lobby'),
    path('tech-check/<str:access_code>/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),
    path('biometric-gate/<str:access_code>/<uuid:attempt_id>/', views.biometric_gate_view, name='biometric_gate'),
    path('api/register-biometrics/<uuid:attempt_id>/', views.register_biometrics, name='register_biometrics'),
    
    # Examen
    path('exam/<str:access_code>/<uuid:attempt_id>/', views.exam_runner_view, name='exam_runner'),
    
    # APIs del Examen
    path('api/save-answer/<uuid:attempt_id>/', views.save_answer, name='save_answer'),
    path('api/log-event/<uuid:attempt_id>/', views.log_event, name='log_event'),
    
    # Timer
    path('api/start-timer/<uuid:attempt_id>/', views.start_exam_timer, name='start_timer'),

    path('submit/<uuid:attempt_id>/', views.submit_exam_view, name='submit_exam'),
    path('finished/<uuid:attempt_id>/', views.exam_finished_view, name='exam_finished'),

    # 3. GESTIÓN
    # Esta es la ruta clave para el botón "Volver":
    path('dashboard/<int:exam_id>/', views.teacher_dashboard_view, name='teacher_dashboard'),
    
    path('attempt/<uuid:attempt_id>/detail/', views.attempt_detail_view, name='attempt_detail'),
    path('pdf_export/<int:exam_id>/', views.descargar_pdf_examen, name='descargar_pdf'),
]
