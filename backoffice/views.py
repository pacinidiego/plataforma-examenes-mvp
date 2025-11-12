import openpyxl
import uuid
import json
from io import BytesIO
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import Rule

from celery.result import AsyncResult
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.core.files.storage import default_storage
from django.http import Http404

import google.generativeai as genai # (S1c) Importamos la librería de IA

from exams.models import Exam, Item
from tenancy.models import TenantMembership
from .tasks import process_exam_excel

# (S1c) Vista del Dashboard (Formulario de subida)
@login_required
def dashboard(request):
    memberships = TenantMembership.objects.filter(user=request.user)
    exam_list = Exam.objects.filter(tenant__in=memberships.values_list('tenant', flat=True)).order_by('-created_at')[:20]

    context = {
        'user': request.user,
        'exam_list': exam_list,
    }
    
    return render(request, 'backoffice/dashboard.html', context)

# --- VISTAS DE CONSTRUCTOR DE ÍTEMS (S1c) ---
@login_required
@require_http_methods(["GET", "POST"])
def item_create(request):
    """
    Maneja la creación de un nuevo Ítem (Pregunta).
    - Si es GET, devuelve el formulario (parcial de HTMX).
    - Si es POST, guarda el ítem y devuelve la fila de la tabla (parcial de HTMX).
    """
    
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        # TODO: Mejorar este manejo de error
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    current_tenant = membership.tenant

    if request.method == "POST":
        # --- Lógica de GUARDADO (POST) ---
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        
        # (S1c v7) Lógica para Opciones de MC (con o sin IA)
        options_json = None
        if item_type == 'MC':
            correct_answer = request.POST.get('correct_answer')
            distractors = request.POST.getlist('distractors') # Obtiene una lista
            
            options_list = []
            # Agregamos la respuesta correcta
            if correct_answer:
                options_list.append({"text": correct_answer, "correct": True})
            # Agregamos los distractores (incorrectos)
            for d in distractors:
                if d: # Nos aseguramos de que no esté vacío
                    options_list.append({"text": d, "correct": False})
            
            options_json = options_list

        new_item = Item.objects.create(
            tenant=current_tenant,
            author=request.user,
            item_type=item_type,
            stem=stem,
            difficulty=difficulty,
            options=options_json
        )
        
        context = {'item': new_item}
        return render(request, 'backoffice/partials/item_table_row.html', context)

    # --- Lógica de Mostrar Formulario (GET) ---
    context = {
        'item_types': Item.ItemType.choices
    }
    return render(request, 'backoffice/partials/item_form.html', context)

# --- ¡NUEVO! VISTA DE IA (S1c - v7) ---
@login_required
@require_http_methods(["POST"])
def ai_generate_distractors(request):
    """
    Llamado por HTMX desde el modal de 'Crear Ítem'.
    Recibe el enunciado y la respuesta correcta, y devuelve
    un parcial de HTML con los 3 distractores generados por IA.
    """
    stem = request.POST.get('stem')
    correct_answer = request.POST.get('correct_answer')

    if not stem or not correct_answer:
        return HttpResponse("<p class='text-red-500'>Por favor, escribe el enunciado y la respuesta correcta primero.</p>")

    try:
        # --- !! ESTA ES LA LÍNEA CORREGIDA !! ---
        # (Cambiamos el nombre del modelo al correcto: gemini-2.5-flash-preview-09-2025)
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        prompt = (
            "Eres un asistente de educación experto en crear exámenes de nivel universitario.\n"
            "Tu tarea es generar 3 opciones incorrectas (distractores) para una pregunta de opción múltiple.\n"
            "Los distractores deben ser plausibles, sutiles y estar relacionados con el tema, evitando opciones obviamente incorrectas.\n"
            "--- CONTEXTO ---\n"
            f"PREGUNTA (ENUNCIADO): \"{stem}\"\n"
            f"RESPUESTA CORRECTA: \"{correct_answer}\"\n"
            "--- TAREA ---\n"
            "Genera 3 distractores. Devuelve ÚNICAMENTE un array JSON de strings, sin nada más.\n"
            "Ejemplo de salida: [\"Distractor 1\", \"Distractor 2\", \"Distractor 3\"]"
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        # Parseamos la respuesta JSON de Gemini
        distractors = json.loads(response.text)
        
        # Nos aseguramos de que sean 3
        if len(distractors) < 3:
            distractors.extend(["", ""]) # Rellenamos si faltan
        
        context = {'distractors': distractors[:3]} # Tomamos solo 3
        return render(request, 'backoffice/partials/distractors.html', context)

    except Exception as e:
        # Esto ahora mostrará el error de la IA (como el 404)
        return HttpResponse(f"<p class='text-red-500'>Error de IA: {e}</p>")


# --- VISTAS DE UPLOAD DE EXCEL (S1c) ---
@login_required
@require_http_methods(["POST"])
def exam_upload_view(request):
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("<p class='text-red-500'>Error: Usuario no tiene un tenant asignado.</p>", status=403)
    
    excel_file = request.FILES.get('excel_file')
    exam_title = request.POST.get('exam_title')

    if not excel_file or not exam_title:
        return HttpResponse("<p class='text-red-500'>Error: Faltan el título o el archivo.</p>", status=400)

    if not excel_file.name.endswith('.xlsx'):
        return HttpResponse(f"<p class='text-red-500'>Error: El archivo debe ser .xlsx. (Subiste: {excel_file.name})</p>", status=400)

    temp_file_name = f"temp/{uuid.uuid4()}.xlsx"
    temp_file_path = default_storage.save(temp_file_name, excel_file)

    task = process_exam_excel.delay(
        tenant_id=membership.tenant.id,
        user_id=request.user.id,
        exam_title=exam_title,
        temp_file_path=temp_file_path
    )
    context = {'task_id': task.id}
    return render(request, 'backoffice/partials/polling_spinner.html', context)


@login_required
def poll_task_status_view(request, task_id):
    task = AsyncResult(task_id)
    if task.state == 'SUCCESS':
        exam_id = task.result 
        redirect_url = reverse('backoffice:exam_constructor', args=[exam_id])
        response = HttpResponse(status=200)
        response['HX-Redirect'] = redirect_url
        return response
    elif task.state == 'FAILURE':
        error_message = str(task.info) 
        return HttpResponse(f"<div class='p-4 bg-red-800 border border-red-600 text-red-100 rounded-md'><p class='font-bold'>Error al procesar el archivo.</p><p class='text-sm mt-2'>{error_message}</p><p class='text-sm mt-2'>Por favor, revise el formato del Excel e intente de nuevo.</p></div>")
    return HttpResponse(status=200)


@login_required
def exam_constructor_view(request, exam_id):
    try:
        exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    except:
        raise Http404("Examen no encontrado o no le pertenece.")
    context = {
        'exam': exam,
        'items': exam.items.all().order_by('examitemlink__order')
    }
    items_html = "<ul>"
    for item in context['items']:
        items_html += f"<li>{item.stem}</li>"
    items_html += "</ul>"
    return HttpResponse(f"<h1>¡Éxito! (S1c)</h1><p>Examen '{exam.title}' creado con {exam.items.count()} ítems.</p>{items_html}<br><a href='{reverse('backoffice:dashboard')}'>Volver al Dashboard</a>")


@login_required
def download_excel_template_view(request):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Plantilla de Examen"
    headers = [
        "tipo", "enunciado", "contenido_caso", 
        "opcion_1", "opcion_2", "opcion_3", "opcion_4", 
        "respuesta_correcta", "dificultad"
    ]
    sheet.append(headers)
    tipo_validation = DataValidation(type="list", formula1='"MC,SHORT,CASE"', allow_blank=True)
    tipo_validation.add('A2:A1000') 
    sheet.add_data_validation(tipo_validation)
    green_fill = PatternFill(start_color="CCFFCC", end_color="CCFFCC", fill_type="solid")
    rule_mc = Rule(type="expression", formula=[f'$A2="MC"'], stopIfTrue=False)
    rule_mc.fill = green_fill
    sheet.conditional_formatting.add('D2:H1000', rule_mc)
    rule_case = Rule(type="expression", formula=[f'$A2="CASE"'], stopIfTrue=False)
    rule_case.fill = green_fill
    sheet.conditional_formatting.add('C2:C1000', rule_case)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_examen_plataforma.xlsx"'
    return response

# --- !! ESTAS VISTAS ESTÁN VACÍAS POR AHORA, PERO LAS NECESITAMOS !! ---
@login_required
def exam_create(request):
    # Placeholder - Lo haremos en el próximo sprint
    return HttpResponse("Página 'exam_create' (POST) (Próximo Sprint)")
