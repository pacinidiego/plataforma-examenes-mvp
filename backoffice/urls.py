from django.urls import path
from . import views

app_name = 'backoffice'

urlpatterns = [
    # --- Dashboard y Filtros ---
    # ESTA LÍNEA FALTABA: Hace que /backoffice/ cargue el dashboard
    path('', views.dashboard, name='dashboard_index'),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    path('items/filter/', views.filter_items, name='filter_items'),

    path('item/<int:item_id>/rotate-difficulty/', views.item_rotate_difficulty, name='item_rotate_difficulty'),

    # --- CRUD de Ítems (Preguntas) ---
    path('item/create/', views.item_create, name='item_create'),
    path('item/<int:pk>/edit/', views.item_edit, name='item_edit'),
    path('item/<int:pk>/delete/', views.item_delete, name='item_delete'),
    # NUEVA RUTA: Borrado Masivo
    path('items/bulk_delete/', views.item_bulk_delete, name='item_bulk_delete'),
    path('item/<int:item_id>/detail/', views.item_detail_view, name='item_detail'),

    # --- CRUD de Exámenes ---
    path('exam/create/', views.exam_create, name='exam_create'),
    path('exam/<int:pk>/delete/', views.exam_delete, name='exam_delete'),
    
    # --- Constructor de Exámenes ---
    path('exam/<int:exam_id>/constructor/', views.exam_constructor_view, name='exam_constructor'),
    path('exam/<int:exam_id>/add/<int:item_id>/', views.add_item_to_exam, name='add_item_to_exam'),
    path('exam/<int:exam_id>/remove/<int:item_id>/', views.remove_item_from_exam, name='remove_item_from_exam'),
    
    # --- Acciones del Constructor ---
    path('exam/<int:exam_id>/update_points/<int:item_id>/', views.item_update_points, name='item_update_points'),
    path('exam/<int:exam_id>/update_title/', views.exam_update_title, name='exam_update_title'),
    
    # --- Publicación ---
    path('exam/<int:exam_id>/publish/', views.exam_publish, name='exam_publish'),
    path('exam/<int:exam_id>/unpublish/', views.exam_unpublish, name='exam_unpublish'),

    # --- IA (Flujo de Curaduría) ---
    path('ai/distractors/', views.ai_generate_distractors, name='ai_generate_distractors'),
    path('exam/<int:exam_id>/ai/preview/', views.ai_preview_items, name='ai_preview_items'),
    path('exam/<int:exam_id>/ai/commit/', views.ai_commit_items, name='ai_commit_items'),

    # --- Placeholders ---
    path('exam/upload/', views.exam_upload_view, name='exam_upload'),
    path('task/<str:task_id>/status/', views.poll_task_status_view, name='poll_task_status'),
    path('download/template/', views.download_excel_template_view, name='download_excel_template'),
]
