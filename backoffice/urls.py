from django.urls import path
from . import views

# (S1c) Rutas para el Backoffice del Docente
app_name = 'backoffice' # Es una buena práctica para HTMX

urlpatterns = [
    # La URL /backoffice/
    path('', views.dashboard, name='dashboard'),
    
    # --- ¡NUEVO! Rutas para el Constructor de Ítems (S1c) ---
    
    # Esta URL entrega el formulario vacío
    # hx-get -> /backoffice/items/create/
    path('items/create/', views.item_create, name='item_create'),
    
    # Esta URL recibe los datos del formulario
    # hx-post -> /backoffice/items/create/
    # (Usamos la misma URL para GET y POST)
]
