from django.shortcuts import render
from django.contrib.auth.decorators import login_required

# (S1/S1c) Importamos los modelos que creamos en el S1
from exams.models import Exam, Item
# (S0b) Importamos los modelos de Tenancy
from tenancy.models import TenantMembership

# (S1b) Vista del Dashboard
@login_required
def dashboard(request):
    """
    Muestra el Dashboard principal del Docente/Admin.
    (S1c): Ahora también muestra las listas de exámenes e ítems.
    """
    
    # TODO: Filtrar por el Tenant del usuario logueado.
    # Por ahora (S1c), el Platform SA (vos) ve todo.
    
    # 1. Obtener los roles/tenants del usuario (para el futuro)
    memberships = TenantMembership.objects.filter(user=request.user)
    
    # 2. Consultar la base de datos (S1c)
    exam_list = Exam.objects.all().order_by('-created_at')[:20] # Últimos 20 exámenes
    item_list = Item.objects.all().order_by('-created_at')[:20] # Últimos 20 ítems

    # Preparamos el contexto para el template
    context = {
        'user': request.user,
        'memberships': memberships,
        'exam_list': exam_list,
        'item_list': item_list,
    }
    
    # Renderiza el template de HTML
    return render(request, 'backoffice/dashboard.html', context)
