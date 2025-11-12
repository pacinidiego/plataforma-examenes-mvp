# backoffice/urls.py
from django.urls import path
from . import views

# (S1c) Rutas para el Backoffice del Docente
app_name = 'backoffice' 

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # --- Constructor de Ítems (S1c) ---
    path('items/create/', views.item_create, name='item_create'),
    
    # --- TAREA 2: Añadimos la URL para editar un ítem ---
    path('item/<int:pk>/edit/', views.item_edit, name='item_edit'),
    
    # --- Constructor de Exámenes (S1c) ---
    # (Esta ruta ya existía y la usaremos para Tarea 1 y 3)
    path('exam/create/', views.exam_create, name='exam_create'),
    path('exam/<int:exam_id>/constructor/', views.exam_constructor_view, name='exam_constructor'),
    
    # --- Tareas Asíncronas (Abandonadas) ---
    path('exam/upload/', views.exam_upload_view, name='exam_upload'),
    path('exam/poll-task/<str:task_id>/', views.poll_task_status_view, name='poll_task_status'),
    path('download-template/', views.download_excel_template_view, name='download_template'),

    # --- Asistente de IA (S1c - v7) ---
    path('ai/generate-distractors/', views.ai_generate_distractors, name='ai_generate_distractors'),
]
