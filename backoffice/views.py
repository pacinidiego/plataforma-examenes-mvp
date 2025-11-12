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

import google.generativeai as genai 

from exams.models import Exam, Item
from tenancy.models import TenantMembership
# (Sacamos la importación de 'tasks' porque abandonamos el Excel)
# from .tasks import process_exam_excel 

# (S1c) Vista del Dashboard
@login_required
def dashboard(request):
    """
    Muestra el Dashboard principal del Docente/Admin.
    """
    # 1. Obtenemos los 'tenants' (universidades) a los que pertenece el usuario
    try:
        memberships = TenantMembership.objects.filter(user=request.user)
        user_tenants = memberships.values_list('tenant', flat=True)
    except Exception:
        # Manejo de error si el usuario no tiene membresía (ej. Superusuario)
        return HttpResponse("Error: No tiene un tenant asignado.", status=403)


    # --- !! ESTA ES LA CORRECCIÓN (BUG #1) !! ---
    # (Filtramos Exámenes E Ítems por los tenants del usuario)
    exam_list = Exam.objects.filter(tenant__in=user_tenants).order_by('-created_at')[:20]
    item_list = Item.objects.filter(tenant__in=user_tenants).order_by('-created_at')[:20]
    # --- !! FIN DE LA CORRECCIÓN !! ---

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

        # (S1c Bugfix "casi igual"): Limpiamos el 'stem' (quitamos espacios extra)
        stem_limpio = " ".join(stem.split())
        
        # (S1c v7) Lógica para Opciones de MC (con o sin IA)
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
            # --- !! CORRECCIÓN (BUG #2) !! ---
            # (Usamos 'iexact' para chequear duplicados ignorando mayúsculas)
            existing_item = Item.objects.filter(
                tenant=current_tenant,
                stem__iexact=stem_limpio  # 'iexact' = case-insensitive exact match
            ).first()
            
            if existing_item:
                # Si existe, devolvemos un error y NO creamos el ítem
                # (Idealmente, esto se mostraría en el modal, pero es un placeholder de error)
                return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe una pregunta con ese enunciado exacto (ignorando mayúsculas).</div>")
            # --- !! FIN DE LA CORRECCIÓN !! ---

            # Usamos el 'stem_limpio' para guardarlo
            new_item = Item.objects.create(
                tenant=current_tenant,
                author=request.user,
                item_type=item_type,
                stem=stem_limpio, 
                difficulty=difficulty,
                options=options_json
            )
            
            # --- !! MODIFICACIÓN S1c Tareas !! ---
            # En lugar de devolver un parcial, redirigimos al dashboard
            # para recargar la lista completa.
            return HttpResponse(headers={'HX-Redirect': reverse('backoffice:dashboard')})
        
        except IntegrityError: # Atrapa el error de la DB (por si acaso)
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe una pregunta con ese enunciado.</div>")
        except Exception as e:
            # Otro error
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> {e}</div>")


    # --- Lógica de Mostrar Formulario (GET) ---
    context = {
        'item_types': Item.ItemType.choices
    }
    return render(request, 'backoffice/partials/item_form.html', context)

# --- !! TAREA 2: NUEVA VISTA PARA EDITAR ÍTEM !! ---
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
    
    # Buscamos el ítem, asegurándonos que pertenezca al tenant del usuario
    item = get_object_or_404(Item, pk=pk, tenant=current_tenant)

    if request.method == "POST":
        # --- Lógica POST (Guardar cambios) ---
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        stem_limpio = " ".join(stem.split())

        # Revisamos duplicados (Bug #2), excluyendo el ítem actual
        existing_item = Item.objects.filter(
            tenant=current_tenant,
            stem__iexact=stem_limpio
        ).exclude(pk=pk).first()

        if existing_item:
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe OTRA pregunta con ese enunciado exacto.</div>")

        # Actualizamos el objeto
        item.item_type = item_type
        item.stem = stem_limpio
        item.difficulty = difficulty
        
        # Re-construimos el JSON de opciones
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

        # Redirigimos al dashboard para ver los cambios
        return HttpResponse(headers={'HX-Redirect': reverse('backoffice:dashboard')})

    # --- Lógica GET (Mostrar formulario pre-rellenado) ---
    correct_answer_text = ""
    distractors_list = ["", "", ""]

    if item.options and item.item_type == 'MC':
        try:
            # Extraemos la respuesta correcta
            correct_answer_text = next(
                (opt['text'] for opt in item.options if opt.get('correct')), 
                ''
            )
            # Extraemos los distractores
            distractors = [opt['text'] for opt in item.options if not opt.get('correct')]
            # Rellenamos la lista para que siempre tenga 3 elementos
            distractors_list = (distractors + ["", "", ""])[:3]
        except (TypeError, KeyError):
            # Si el JSON está malformado, lo dejamos en blanco
            pass 

    context = {
        'item': item,
        'item_types': Item.ItemType.choices,
        'correct_answer_text': correct_answer_text,
        'distractors_list': distractors_list
    }
    return render(request, 'backoffice/partials/item_form.html', context)
# --- !! FIN TAREA 2 !! ---


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
# (Dejamos estas funciones pero las 'apagamos' para no romper las URLs)

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

@login_required
def exam_constructor_view(request, exam_id):
    # (Placeholder - Próximo sprint)
    try:
        # Aseguramos que el examen pertenezca al tenant del usuario
        exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    except:
        raise Http404("Examen no encontrado o no le pertenece.")
    return HttpResponse(f"<h1>Placeholder (S2)</h1><p>Esta será la página del Constructor para el Examen: '{exam.title}'.</p><br><a href='{reverse('backoffice:dashboard')}'>Volver al Dashboard</a>")

# --- !! TAREA 1: IMPLEMENTACIÓN DE EXAM_CREATE !! ---
@login_required
@require_http_methods(["GET", "POST"])
def exam_create(request):
    """
    Maneja la creación de un nuevo Examen (solo título).
    GET: Muestra el modal.
    POST: Crea el examen y redirige al constructor.
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
        
        # Tarea 1: Redirigimos al constructor (S2)
        redirect_url = reverse('backoffice:exam_constructor', args=[exam.id])
        return HttpResponse(headers={'HX-Redirect': redirect_url})

    # Si es GET, solo mostramos el modal nuevo
    return render(request, 'backoffice/partials/exam_form.html')
# --- !! FIN TAREA 1 !! ---
