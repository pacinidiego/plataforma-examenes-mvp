from django.urls import path
from . import views

app_name = 'backoffice'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # CRUD de Items (Preguntas)
    path('item/create/', views.item_create, name='item_create'),
    path('item/<int:pk>/edit/', views.item_edit, name='item_edit'),
    path('item/<int:pk>/delete/', views.item_delete, name='item_delete'),
    path('item/<int:item_id>/detail/', views.item_detail_view, name='item_detail'),
    
    # CRUD de Exámenes
    path('exam/create/', views.exam_create, name='exam_create'),
    path('exam/<int:pk>/delete/', views.exam_delete, name='exam_delete'),
    
    # Constructor
    path('exam/<int:exam_id>/constructor/', views.exam_constructor_view, name='exam_constructor'),
    
    # [NUEVA URL S1e] Publicar el examen
    path('exam/<int:exam_id>/publish/', views.exam_publish, name='exam_publish'),
    
    # Acciones del Constructor
    path('exam/<int:exam_id>/add/<int:item_id>/', views.add_item_to_exam, name='add_item_to_exam'),
    path('exam/<int:exam_id>/remove/<int:item_id>/', views.remove_item_from_exam, name='remove_item_from_exam'),
    
    # Filtros y Asistentes IA
    path('filter-items/', views.filter_items, name='filter_items'),
    path('ai/distractors/', views.ai_generate_distractors, name='ai_generate_distractors'),
    path('exam/<int:exam_id>/ai-suggest/', views.ai_suggest_items, name='ai_suggest_items'),
]
