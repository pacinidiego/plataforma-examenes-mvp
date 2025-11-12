from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse

# (S1/S1c) Importamos los modelos
from exams.models import Exam, Item
from tenancy.models import TenantMembership

# (S1b) Vista del Dashboard
@login_required
def dashboard(request):
    """
    Muestra el Dashboard principal del Docente/Admin.
    (S1c): Ahora también muestra las listas de exámenes e ítems.
    """
    # TODO: Filtrar por el Tenant del usuario logueado.
    memberships = TenantMembership.objects.filter(user=request.user)
    
    # Consultar la base de datos (S1c)
    exam_list = Exam.objects.all().order_by('-created_at')[:20]
    item_list = Item.objects.all().order_by('-created_at')[:20]

    context = {
        'user': request.user,
        'memberships': memberships,
        'exam_list': exam_list,
        'item_list': item_list,
    }
    
    return render(request, 'backoffice/dashboard.html', context)

# --- ¡NUEVO! Vistas del Constructor de Ítems (S1c) ---

@login_required
@require_http_methods(["GET", "POST"]) # Esta vista maneja GET y POST
def item_create(request):
    """
    Maneja la creación de un nuevo Ítem (Pregunta).
    - Si es GET, devuelve el formulario (parcial de HTMX).
    - Si es POST, guarda el ítem y devuelve la fila de la tabla (parcial de HTMX).
    """
    
    # TODO: Asegurarnos de asignar el Tenant del usuario.
    # Por ahora, asignamos el primer Tenant que encontramos (el tuyo).
    current_tenant = TenantMembership.objects.filter(user=request.user).first().tenant

    if request.method == "POST":
        # --- Lógica de GUARDADO (POST) ---
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        
        # (Spec S1: Creamos el Ítem en la base de datos)
        new_item = Item.objects.create(
            tenant=current_tenant,
            author=request.user,
            item_type=item_type,
            stem=stem,
            difficulty=difficulty
            # TODO: Guardar 'options' para MC
        )
        
        # Respuesta HTMX: Devolvemos la fila de la tabla
        # Esto le dice a HTMX: "Cierra el modal y agrega esta fila a la tabla"
        # (Usamos un template parcial para la fila)
        context = {'item': new_item}
        return render(request, 'backoffice/partials/item_table_row.html', context)

    # --- Lógica de Mostrar Formulario (GET) ---
    # Si es un GET, solo mostramos el formulario
    context = {
        'item_types': Item.ItemType.choices
    }
    return render(request, 'backoffice/partials/item_form.html', context)
