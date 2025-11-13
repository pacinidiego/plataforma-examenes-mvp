# backoffice/views.py
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
from django.db import IntegrityError # (S1c Bugfix 2) Para atrapar el error de duplicado
from django.db.models import Count, Q

import google.generativeai as genai 

from exams.models import Exam, Item, ExamItemLink
from tenancy.models import TenantMembership

# (S1c) Vista del Dashboard
@login_required
def dashboard(request):
    """
    Muestra el Dashboard principal del Docente/Admin.
    """
    try:
        memberships = TenantMembership.objects.filter(user=request.user)
        user_tenants = memberships.values_list('tenant', flat=True)
    except Exception:
        return HttpResponse("Error: No tiene un tenant asignado.", status=403)

    exam_list = Exam.objects.filter(tenant__in=user_tenants).order_by('-created_at')[:20]
    
    item_list = Item.objects.filter(tenant__in=user_tenants)\
                            .annotate(in_use_count=Count('exams'))\
                            .order_by('-created_at')[:20]

    context = {
        'user': request.user,
        'memberships': memberships,
        'exam_list': exam_list,
        'item_list': item_list,
    }
    
    return render(request, 'backoffice/dashboard.html', context)

# --- VISTAS DE CONSTRUCTOR DE ÍTEMS (S1c) ---
@login_required
@require_http_methods(["GET", "POST"])
def item_create(request):
    """
    Maneja la creación de un nuevo Ítem (Pregunta).
    """
    
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    current_tenant = membership.tenant

    if request.method == "POST":
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        stem_limpio = " ".join(stem.split())
        
        options_json = None
        if item_type == 'MC':
            correct_answer = request.POST.get('correct_answer')
            distractors = request.POST.getlist('distractors')
            
            options_list = []
            if correct_answer:
                options_list.append({"text": correct_answer, "correct": True})
            for d in distractors:
                if d: 
                    options_list.append({"text": d, "correct": False})
            
            options_json = options_list

        try:
            existing_item = Item.objects.filter(
                tenant=current_tenant,
                stem__iexact=stem_limpio
            ).first()
            
            if existing_item:
                return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe una pregunta con ese enunciado exacto (ignorando mayúsculas).</div>")

            new_item = Item.objects.create(
                tenant=current_tenant,
                author=request.user,
                item_type=item_type,
                stem=stem_limpio, 
                difficulty=difficulty,
                options=options_json
            )
            
            return HttpResponse(headers={'HX-Redirect': reverse('backoffice:dashboard')})
        
        except IntegrityError:
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe una pregunta con ese enunciado.</div>")
        except Exception as e:
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> {e}</div>")

    context = {
        'item_types': Item.ItemType.choices
    }
    return render(request, 'backoffice/partials/item_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def item_edit(request, pk):
    """
    Maneja la edición de un Ítem (Pregunta) existente.
    """
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    current_tenant = membership.tenant
    
    item = get_object_or_404(Item, pk=pk, tenant=current_tenant)

    if request.method == "POST":
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        stem_limpio = " ".join(stem.split())

        existing_item = Item.objects.filter(
            tenant=current_tenant,
            stem__iexact=stem_limpio
        ).exclude(pk=pk).first()

        if existing_item:
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe OTRA pregunta con ese enunciado exacto.</div>")

        item.item_type = item_type
        item.stem = stem_limpio
        item.difficulty = difficulty
        
        options_json = None
        if item_type == 'MC':
            correct_answer = request.POST.get('correct_answer')
            distractors = request.POST.getlist('distractors')
            
            options_list = []
            if correct_answer:
                options_list.append({"text": correct_answer, "correct": True})
            for d in distractors:
                if d: 
                    options_list.append({"text": d, "correct": False})
            options_json = options_list
        
        item.options = options_json
        item.save()

        return HttpResponse(headers={'HX-Redirect': reverse('backoffice:dashboard')})

    correct_answer_text = ""
    distractors_list = ["", "", ""]

    if item.options and item.item_type == 'MC':
        try:
            correct_answer_text = next(
                (opt['text'] for opt in item.options if opt.get('correct')), 
                ''
            )
            distractors = [opt['text'] for opt in item.options if not opt.get('correct')]
            distractors_list = (distractors + ["", "", ""])[:3]
        except (TypeError, KeyError):
            pass 

    context = {
        'item': item,
        'item_types': Item.ItemType.choices,
        'correct_answer_text': correct_answer_text,
        'distractors_list': distractors_list
    }
    return render(request, 'backoffice/partials/item_form.html', context)


# --- VISTA DE IA (S1c - v7) ---
@login_required
@require_http_methods(["POST"])
def ai_generate_distractors(request):
    """
    Llamado por HTMX desde el modal de 'Crear Ítem'.
    """
    stem = request.POST.get('stem')
    correct_answer = request.POST.get('correct_answer')

    if not stem or not correct_answer:
        return HttpResponse("<p class='text-red-500'>Por favor, escribe el enunciado y la respuesta correcta primero.</p>")

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        prompt = (
            "Eres un asistente de educación experto en crear exámenes de nivel universitario.\n"
            "Tu tarea es generar 3 opciones **inequívocamente incorrectas** (distractores) para una pregunta de opción múltiple.\n"
            "Los distractores deben ser plausibles y estar relacionados con el tema, pero ser claramente erróneos.\n"
            "**REGLA CRÍTICA:** No sugieras distractores que sean sinónimos o ejemplos alternativos que *también* sean correctos.\n"
            "**Ejemplo de REGLA CRÍTICA:** Si la pregunta es 'un protocolo de capa 4' y la respuesta correcta es 'TCP', NO debes sugerir 'UDP' como distractor, ya que 'UDP' también es una respuesta correcta de capa 4.\n"
            "\n"
            "--- CONTEXTO ---\n"
            f"PREGUNTA (ENUNCIADO): \"{stem}\"\n"
            f"RESPUESTA CORRECTA: \"{correct_answer}\"\n"
            "\n"
            "--- TAREA ---\n"
            "Genera 3 distractores **inequívocamente incorrectos**. Devuelve ÚNICAMENTE un array JSON de strings, sin nada más.\n"
            "Ejemplo de salida (para el contexto 'TCP'): [\"IP\", \"HTTP\", \"FTP\"]"
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        distractors = json.loads(response.text)
        
        if len(distractors) < 3:
            distractors.extend(["", ""]) 
        
        context = {'distractors': distractors[:3]} 
        return render(request, 'backoffice/partials/distractors.html', context)

    except Exception as e:
        return HttpResponse(f"<p class='text-red-500'>Error de IA: {e}</p>")


# --- VISTAS DE UPLOAD DE EXCEL (S1c - Abandonadas) ---
@login_required
def exam_upload_view(request):
    return HttpResponse("Esta función (upload Excel) ha sido desactivada.", status=403)

@login_required
def poll_task_status_view(request, task_id):
    return HttpResponse("Esta función (upload Excel) ha sido desactivada.", status=403)

@login_required
def download_excel_template_view(request):
    return HttpResponse("Esta función (upload Excel) ha sido desactivada.", status=403)

# --- VISTAS DEL CONSTRUCTOR DE EXÁMENES (S1c-v7) ---

# --- !! INICIO SPRINT S1d (Paso 1) !! ---
# (Helper para obtener el contexto del constructor)
def _get_constructor_context(request, exam_id):
    """
    Función helper para obtener el contexto de las dos columnas
    (preguntas en el examen vs. preguntas en el banco).
    """
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    current_tenant = exam.tenant
    
    # 1. Preguntas que YA están en el examen
    exam_items = exam.items.all().order_by('examitemlink__order')
    
    # 2. Preguntas del banco que NO están en el examen
    bank_items = Item.objects.filter(tenant=current_tenant)\
                             .exclude(id__in=exam_items.values_list('id', flat=True))\
                             .order_by('-created_at')
                             
    return {
        'exam': exam,
        'exam_items': exam_items,
        'bank_items': bank_items,
        'exam_items_count': exam_items.count(),
        'bank_items_count': bank_items.count(),
    }

@login_required
def exam_constructor_view(request, exam_id):
    """
    Vista principal del Constructor. 
    Reemplaza el 'Placeholder (S2)'.
    """
    try:
        context = _get_constructor_context(request, exam_id)
        return render(request, 'backoffice/constructor.html', context)
    except Http404:
        return HttpResponse("Examen no encontrado o no le pertenece.", status=404)
    except Exception as e:
        return HttpResponse(f"Error: {e}", status=500)


@login_required
@require_http_methods(["POST"])
def add_item_to_exam(request, exam_id, item_id):
    """
    Vista HTMX para AÑADIR un ítem al examen.
    """
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    item = get_object_or_404(Item, id=item_id, tenant=exam.tenant)
    
    ExamItemLink.objects.get_or_create(exam=exam, item=item)
    
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_body.html', context)


@login_required
@require_http_methods(["POST"])
def remove_item_from_exam(request, exam_id, item_id):
    """
    Vista HTMX para QUITAR un ítem del examen.
    """
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    
    ExamItemLink.objects.filter(exam=exam, item_id=item_id).delete()
    
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_body.html', context)
# --- !! FIN SPRINT S1d (Paso 1) !! ---


@login_required
@require_http_methods(["GET", "POST"])
def exam_create(request):
    """
    Maneja la creación de un nuevo Examen (solo título).
    """
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    current_tenant = membership.tenant

    if request.method == "POST":
        title = request.POST.get('title', 'Examen sin título').strip()
        
        exam = Exam.objects.create(
            tenant=current_tenant,
            author=request.user,
            title=title
        )
        
        redirect_url = reverse('backoffice:exam_constructor', args=[exam.id])
        return HttpResponse(headers={'HX-Redirect': redirect_url})

    return render(request, 'backoffice/partials/exam_form.html')

# --- !! INICIO SPRINT S1d (Paso 2: Gestión) !! ---
@login_required
@require_http_methods(["POST"])
def exam_delete(request, pk):
    """
    Vista HTMX para BORRAR un examen.
    """
    try:
        exam = get_object_or_404(Exam, pk=pk, tenant__memberships__user=request.user)
        exam.delete()
        return HttpResponse("", status=200)
    except Http404:
        return HttpResponse("Examen no encontrado o no le pertenece.", status=404)

@login_required
@require_http_methods(["POST"])
def item_delete(request, pk):
    """
    Vista HTMX para BORRAR una pregunta del banco.
    """
    try:
        item = get_object_or_404(Item, pk=pk, tenant__memberships__user=request.user)
        item.delete()
        return HttpResponse("", status=200)
    except Http404:
        return HttpResponse("Ítem no encontrado o no le pertenece.", status=404)
# --- !! FIN SPRINT S1d (Paso 2) !! ---


# --- !! INICIO SPRINT S1d (Paso 3: IA y Filtros) !! ---
@login_required
@require_http_methods(["GET"])
def filter_items(request):
    """
    Vista HTMX para filtrar el Banco de Preguntas en el Dashboard.
    """
    try:
        memberships = TenantMembership.objects.filter(user=request.user)
        user_tenants = memberships.values_list('tenant', flat=True)
    except Exception:
        return HttpResponse("Error: No tiene un tenant asignado.", status=403)

    filter_type = request.GET.get('filter', 'all')
    
    # Query base
    base_query = Item.objects.filter(tenant__in=user_tenants)
    
    if filter_type == 'in_use':
        # Filtra ítems que están en al menos 1 examen
        base_query = base_query.annotate(in_use_count=Count('exams')).filter(in_use_count__gt=0)
    elif filter_type == 'not_in_use':
        # Filtra ítems que no están en ningún examen
        base_query = base_query.annotate(in_use_count=Count('exams')).filter(in_use_count=0)
    else:
        # 'all' - solo anota
        base_query = base_query.annotate(in_use_count=Count('exams'))

    item_list = base_query.order_by('-created_at')

    context = {
        'item_list': item_list,
    }
    # Devolvemos solo el parcial de la tabla
    return render(request, 'backoffice/partials/_item_table_body.html', context)


@login_required
@require_http_methods(["POST"])
def ai_suggest_items(request, exam_id):
    """
    Vista HTMX para el Asistente de IA en el Constructor.
    """
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    user_prompt = request.POST.get('ai_prompt')

    if not user_prompt:
        context = _get_constructor_context(request, exam_id)
        return render(request, 'backoffice/partials/_constructor_body.html', context)
    
    context = _get_constructor_context(request, exam_id)
    bank_items = context['bank_items']
    
    available_items_data = []
    for item in bank_items:
        available_items_data.append({
            "id": item.id,
            "stem": item.stem,
            "tags": item.tags
        })

    if not available_items_data:
        context = _get_constructor_context(request, exam_id)
        return render(request, 'backoffice/partials/_constructor_body.html', context)

    # 3. Creamos el Prompt para Gemini
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        prompt = (
            "Eres un asistente de profesor experto en construir exámenes.\n"
            "Tu tarea es seleccionar preguntas de una lista de preguntas disponibles en un 'Banco de Preguntas', basándote en la petición de un usuario.\n"
            "\n"
            "--- PETICIÓN DEL USUARIO ---\n"
            f"\"{user_prompt}\"\n"
            "\n"
            "--- PREGUNTAS DISPONIBLES EN EL BANCO (formato: [id, enunciado, etiquetas]) ---\n"
            f"{json.dumps(available_items_data)}\n"
            "\n"
            "--- TAREA ---\n"
            "Analiza la petición del usuario y compárala con las preguntas disponibles. Devuelve ÚNICAMENTE un array JSON de los IDs de las preguntas que mejor coinciden.\n"
            "Ejemplo de salida: [15, 22, 43]"
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        suggested_ids = json.loads(response.text)
        
        if suggested_ids:
            items_to_add = Item.objects.filter(
                id__in=suggested_ids, 
                tenant=exam.tenant
            )
            for item in items_to_add:
                ExamItemLink.objects.get_or_create(exam=exam, item=item)
    
    # --- !! INICIO S1d (Debug IA) !! ---
    except Exception as e:
        # En lugar de fallar silenciosamente, devolvemos el error al usuario
        # para que podamos ver qué está fallando (ej. mal JSON de la IA).
        error_html = f"""
        <div class="p-4 bg-red-800 text-red-100 rounded-lg col-span-2">
            <h3 class="font-bold">Error al contactar la IA</h3>
            <p>La IA falló al procesar tu petición. Esto suele pasar si el prompt es muy complejo o si la IA no devuelve un formato JSON válido.</p>
            <p class="mt-2 font-mono text-sm"><strong>Error:</strong> {e}</p>
        </div>
        """
        # Devolvemos el error, que reemplazará el constructor-body
        return HttpResponse(error_html)
    # --- !! FIN S1d (Debug IA) !! ---

    # Si el 'try' tuvo éxito, devolvemos el cuerpo actualizado
    updated_context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_body.html', updated_context)
# --- !! FIN SL1d (Paso 3: IA y Filtros) !! ---
