from django.urls import path
from . import views

# (S1c) Rutas para el Backoffice del Docente
app_name = 'backoffice' 

urlpatterns = [
    # Dashboard (que ahora será el formulario de subida)
    path('', views.dashboard, name='dashboard'),
    
    # --- ¡NUEVO! Flujo de subida de Excel (S1c) ---
    
    # 1. (POST) Recibe el archivo Excel y dispara la tarea de Celery
    path('exam/upload/', views.exam_upload_view, name='exam_upload'),
    
    # 2. (GET) La URL que HTMX "pollea" (pregunta) para ver si la tarea terminó
    path('exam/poll-task/<str:task_id>/', views.poll_task_status_view, name='poll_task_status'),
    
    # 3. (GET) La página del "Constructor" (la "versión no grabada")
    path('exam/<int:exam_id>/constructor/', views.exam_constructor_view, name='exam_constructor'),
    
    # 4. (GET) La URL para descargar la plantilla modelo
    path('download-template/', views.download_excel_template_view, name='download_template'),
]
