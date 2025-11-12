import openpyxl
import uuid
from io import BytesIO
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from celery.result import AsyncResult
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.core.files.storage import default_storage
from django.http import Http404

# (S1/S1c) Importamos los modelos
from exams.models import Exam, Item
from tenancy.models import TenantMembership
from .tasks import process_exam_excel # ¡Importamos el worker!

# (S1c) Vista del Dashboard (Ahora es el formulario de subida)
@login_required
def dashboard(request):
    """
    Muestra el Dashboard principal del Docente/Admin.
    (S1c): Ahora es el formulario para subir exámenes de Excel.
    """
    # TODO: Filtrar por Tenant
    exam_list = Exam.objects.all().order_by('-created_at')[:20]

    context = {
        'user': request.user,
        'exam_list': exam_list,
    }
    
    return render(request, 'backoffice/dashboard.html', context)

# --- ¡NUEVO! VISTAS DE UPLOAD DE EXCEL (S1c) ---

@login_required
@require_http_methods(["POST"])
def exam_upload_view(request):
    """
    (Paso A)
    Recibe el POST del formulario de subida (con HTMX).
    Guarda el archivo en S3/R2 temporalmente y lanza la tarea de Celery.
    Devuelve el 'spinner' de polling.
    """
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    
    excel_file = request.FILES.get('excel_file')
    exam_title = request.POST.get('exam_title')

    if not excel_file or not exam_title:
        # TODO: Mejorar manejo de error
        return HttpResponse("Error: Faltan datos.", status=400)

    # 1. Guardar el archivo temporalmente en S3/R2 (en una carpeta 'temp')
    # (Usamos un UUID para un nombre único)
    temp_file_name = f"temp/{uuid.uuid4()}.xlsx"
    temp_file_path = default_storage.save(temp_file_name, excel_file)

    # 2. Lanzar la tarea de Celery (Paso B)
    task = process_exam_excel.delay(
        tenant_id=membership.tenant.id,
        user_id=request.user.id,
        exam_title=exam_title,
        temp_file_path=temp_file_path
    )

    # 3. Devolver el 'spinner' de polling (Paso C)
    # Este HTML le dice a HTMX que empiece a preguntar a la URL de 'poll_task_status'
    context = {'task_id': task.id}
    return render(request, 'backoffice/partials/polling_spinner.html', context)


@login_required
def poll_task_status_view(request, task_id):
    """
    (Paso C)
    Esta es la URL que HTMX 'pollea' (pregunta) cada 2 segundos.
    Verifica el estado de la tarea de Celery.
    """
    task = AsyncResult(task_id)
    
    if task.state == 'SUCCESS':
        # ¡TAREA COMPLETA! (Paso D)
        exam_id = task.result # El worker nos devuelve el ID del examen
        
        # Le decimos a HTMX que redirija al usuario
        redirect_url = reverse('backoffice:exam_constructor', args=[exam_id])
        response = HttpResponse(status=200)
        response['HX-Redirect'] = redirect_url
        return response
        
    elif task.state == 'FAILURE':
        # TODO: Manejar el error
        return HttpResponse(f"<p class='text-red-500'>Error al procesar el archivo. Por favor, revise el formato e intente de nuevo.</p>")

    # Tarea aún en progreso (PENDING o STARTED)
    # Devolvemos un 200 OK vacío. HTMX seguirá preguntando.
    return HttpResponse(status=200)


@login_required
def exam_constructor_view(request, exam_id):
    """
    (Paso E)
    La página de "versión subida pero no grabada".
    (Por ahora, solo es un placeholder).
    """
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    
    context = {
        'exam': exam,
        'items': exam.items.all().order_by('examitemlink__order')
    }
    
    # TODO: Crear este template
    # return render(request, 'backoffice/exam_constructor.html', context)
    return HttpResponse(f"<h1>¡Éxito! (S1c)</h1><p>Examen '{exam.title}' creado con {exam.items.count()} ítems.</p><a href='{reverse('backoffice:dashboard')}'>Volver al Dashboard</a>")


@login_required
def download_excel_template_view(request):
    """
    (Tu Req 1)
    Genera y sirve la plantilla de Excel "inteligente"
    con validación de datos (dropdown) y formato condicional (colores).
    """
    # 1. Crear un workbook en memoria
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Plantilla de Examen"

    # 2. Definir Cabeceras
    headers = [
        "tipo", "enunciado", "contenido_caso", 
        "opcion_1", "opcion_2", "opcion_3", "opcion_4", 
        "respuesta_correcta", "dificultad"
    ]
    sheet.append(headers)

    # 3. Validar Columna "tipo" (Dropdown)
    tipo_validation = DataValidation(type="list", formula1='"MC,SHORT,CASE"', allow_blank=True)
    tipo_validation.add('A2:A1000') # Aplica a 1000 filas
    sheet.add_data_validation(tipo_validation)

    # 4. Formato Condicional (Colores)
    # (Esta es tu idea, pintamos según el tipo)
    green_fill = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")
    
    # Si A2="MC", pinta D2:H2 (Opciones y Respuesta)
    sheet.conditional_formatting.add('D2:H1000', 
        formula=[f'$A2="MC"'], stopIfTrue=False, fill=green_fill)
        
    # Si A2="CASE", pinta C2 (Contenido del Caso)
    sheet.conditional_formatting.add('C2:C1000', 
        formula=[f'$A2="CASE"'], stopIfTrue=False, fill=green_fill)
    
    # 5. Guardar en un buffer de memoria
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    
    # 6. Servir el archivo
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_examen_plataforma.xlsx"'
    return response
