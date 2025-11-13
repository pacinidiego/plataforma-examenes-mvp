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
    path('item/<int:pk>/edit/', views.item_edit, name='item_edit'),
    
    # --- Constructor de Exámenes (S1c / S1d) ---
    path('exam/create/', views.exam_create, name='exam_create'),
    path('exam/<int:exam_id>/constructor/', views.exam_constructor_view, name='exam_constructor'),
    
    # --- !! INICIO SPRINT S1d (Paso 1) !! ---
    # (Rutas HTMX para el constructor)
    path('exam/<int:exam_id>/add/<int:item_id>/', 
         views.add_item_to_exam, 
         name='add_item_to_exam'),
         
    path('exam/<int:exam_id>/remove/<int:item_id>/', 
         views.remove_item_from_exam, 
         name='remove_item_from_exam'),
    # --- !! FIN SPRINT S1d (Paso 1) !! ---

    # --- !! INICIO SPRINT S1d (Paso 2: Gestión) !! ---
    path('exam/<int:pk>/delete/', 
         views.exam_delete, 
         name='exam_delete'),
         
    path('item/<int:pk>/delete/', 
         views.item_delete, 
         name='item_delete'),
    # --- !! FIN SPRINT S1d (Paso 2) !! ---

    # --- !! INICIO SPRINT S1d (Paso 3: IA y Filtros) !! ---
    path('items/filter/', 
         views.filter_items, 
         name='filter_items'),
         
    path('exam/<int:exam_id>/ai-suggest/', 
         views.ai_suggest_items, 
         name='ai_suggest_items'),
    # --- !! FIN SPRINT S1d (Paso 3) !! ---

    # --- Tareas Asíncronas (Abandonadas) ---
    path('exam/upload/', views.exam_upload_view, name='exam_upload'),
    path('exam/poll-task/<str:task_id>/', views.poll_task_status_view, name='poll_task_status'),
    path('download-template/', views.download_excel_template_view, name='download_template'),

    # --- Asistente de IA (S1c - v7) ---
    path('ai/generate-distractors/', views.ai_generate_distractors, name='ai_generate_distractors'),
]
