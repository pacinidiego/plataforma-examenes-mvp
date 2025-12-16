from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    # --- RUTAS DE ALUMNO ---
   # path('lobby/<str:access_code>/', views.lobby_view, name='lobby'),
    path('tech-check/<str:access_code>/<uuid:attempt_id>/', views.tech_check_view, name='tech_check'),
    
    # Biometría
    path('biometric-gate/<str:access_code>/<uuid:attempt_id>/', views.biometric_gate_view, name='biometric_gate'),
    path('api/register-biometrics/<uuid:attempt_id>/', views.register_biometrics, name='register_biometrics'),
    
    # Examen
    path('exam/<str:access_code>/<uuid:attempt_id>/', views.exam_runner_view, name='exam_runner'),
    path('api/save-answer/<uuid:attempt_id>/', views.save_answer, name='save_answer'),
    path('api/log-event/<uuid:attempt_id>/', views.log_event, name='log_event'),
    path('submit/<uuid:attempt_id>/', views.submit_exam_view, name='submit_exam'),
    path('finished/<uuid:attempt_id>/', views.exam_finished_view, name='exam_finished'),

    # --- RUTAS DE DOCENTE ---
    path('dashboard/<int:exam_id>/', views.teacher_dashboard_view, name='teacher_dashboard'),
    path('attempt/<uuid:attempt_id>/detail/', views.attempt_detail_view, name='attempt_detail'),

    # --- NUEVA RUTA: EL PORTAL UNIFICADO ---
    path('portal/', views.portal_docente_view, name='portal_docente'),

    # LA PUERTA DE ENTRADA
    path('teacher/', views.teacher_home_view, name='teacher_home'),

    # --- NUEVA RUTA: EXPORTAR PDF ---
    path('pdf_export/<int:exam_id>/', views.descargar_pdf_examen, name='descargar_pdf'),
]
