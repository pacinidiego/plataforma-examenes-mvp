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
from django.db import IntegrityError 
from django.db.models import Count, Q, Sum 
from django.contrib import messages 
from django.utils import timezone 
from django.contrib.postgres.aggregates import StringAgg 

import google.generativeai as genai 

from exams.models import Exam, Item, ExamItemLink
from tenancy.models import TenantMembership

# (S1c) Vista del Dashboard
@login_required
def dashboard(request):
    try:
        memberships = TenantMembership.objects.filter(user=request.user)
        user_tenants = memberships.values_list('tenant', flat=True)
        if not memberships.exists():
            return HttpResponse("Error: No tiene un tenant asignado.", status=403)
            
    except Exception:
        return HttpResponse("Error: No se pudo verificar la membresía del tenant.", status=500)

    exam_list = Exam.objects.filter(tenant__in=user_tenants).order_by('-created_at')[:20]
    
    item_list = Item.objects.filter(tenant__in=user_tenants)\
                            .annotate(
                                in_use_count=Count('exams'),
                                exam_titles=StringAgg('exams__title', delimiter=', ', distinct=True)
                            )\
                            .order_by('-created_at')[:20]

    context = {
        'user': request.user,
        'memberships': memberships,
        'exam_list': exam_list,
        'item_list': item_list,
        'active_filter': 'all', 
    }
    return render(request, 'backoffice/dashboard.html', context)

# --- VISTAS DE CONSTRUCTOR DE ÍTEMS ---
@login_required
@require_http_methods(["GET", "POST"])
def item_create(request):
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    current_tenant = membership.tenant

    if request.method == "POST":
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        # Tags opcionales (agregado reciente)
        tags = request.POST.get('tags', '').strip()
        
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
                return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe una pregunta con ese enunciado exacto.</div>")

            new_item = Item.objects.create(
                tenant=current_tenant,
                author=request.user,
                item_type=item_type,
                stem=stem_limpio, 
                difficulty=difficulty,
                options=options_json,
                tags=tags
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
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status=403)
    current_tenant = membership.tenant
    
    item = get_object_or_404(Item, pk=pk, tenant=current_tenant)

    if request.method == "POST":
        item_type = request.POST.get('item_type')
        stem = request.POST.get('stem')
        difficulty = request.POST.get('difficulty')
        tags = request.POST.get('tags', '').strip()
        stem_limpio = " ".join(stem.split())

        existing_item = Item.objects.filter(
            tenant=current_tenant,
            stem__iexact=stem_limpio
        ).exclude(pk=pk).first()

        if existing_item:
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe OTRA pregunta con ese enunciado.</div>")

        item.item_type = item_type
        item.stem = stem_limpio
        item.difficulty = difficulty
        item.tags = tags
        
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


@login_required
@require_http_methods(["POST"])
def ai_generate_distractors(request):
    stem = request.POST.get('stem')
    correct_answer = request.POST.get('correct_answer')

    if not stem or not correct_answer:
        return HttpResponse("<p class='text-red-500'>Por favor, escribe el enunciado y la respuesta correcta primero.</p>")

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        prompt = (
            "Eres un asistente de educación experto en crear exámenes.\n"
            f"Genera 3 distractores incorrectos para: P: \"{stem}\" R: \"{correct_answer}\".\n"
            "Devuelve solo un array JSON de strings: [\"D1\", \"D2\", \"D3\"]"
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

@login_required
def exam_upload_view(request):
    return HttpResponse("Desactivado.", status=403)

@login_required
def poll_task_status_view(request, task_id):
    return HttpResponse("Desactivado.", status=403)

@login_required
def download_excel_template_view(request):
    return HttpResponse("Desactivado.", status=403)


# --- CONSTRUCTOR DE EXÁMENES ---

def _get_constructor_context(request, exam_id, highlight_map=None):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    current_tenant = exam.tenant
    
    exam_links = ExamItemLink.objects.filter(exam=exam).select_related('item').order_by('order')
    total_points = exam_links.aggregate(Sum('points'))['points__sum'] or 0.0
    exam_item_ids = exam_links.values_list('item_id', flat=True)

    bank_items = Item.objects.filter(tenant=current_tenant)\
                             .exclude(id__in=exam_item_ids)\
                             .order_by('-created_at')
    
    if highlight_map:
        for item in bank_items:
            item.source_tag = highlight_map.get(item.id, None)
                             
    return {
        'exam': exam,
        'exam_links': exam_links,
        'bank_items': bank_items,
        'exam_items_count': exam_links.count(),
        'bank_items_count': bank_items.count(),
        'total_points': total_points,
    }

@login_required
def exam_constructor_view(request, exam_id):
    try:
        context = _get_constructor_context(request, exam_id)
        return render(request, 'backoffice/constructor.html', context)
    except Http404:
        return HttpResponse("Examen no encontrado.", status=404)
    except Exception as e:
        return HttpResponse(f"Error: {e}", status=500)

# --- ACCIONES DEL CONSTRUCTOR ---

@login_required
@require_http_methods(["POST"])
def add_item_to_exam(request, exam_id, item_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    item = get_object_or_404(Item, id=item_id, tenant=exam.tenant)
    ExamItemLink.objects.get_or_create(exam=exam, item=item)
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_oob_update.html', context)

@login_required
@require_http_methods(["POST"])
def remove_item_from_exam(request, exam_id, item_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    ExamItemLink.objects.filter(exam=exam, item_id=item_id).delete()
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_oob_update.html', context)

@login_required
@require_http_methods(["POST"])
def exam_update_title(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    new_title = request.POST.get('title', '').strip()
    if new_title:
        exam.title = new_title
        exam.save()
    return HttpResponse(status=204)

@login_required
@require_http_methods(["POST"])
def item_update_points(request, exam_id, item_id):
    link = get_object_or_404(ExamItemLink, exam_id=exam_id, item_id=item_id)
    try:
        new_points = float(request.POST.get('points', 0))
        if new_points < 0: new_points = 0
    except ValueError:
        new_points = 0
    link.points = new_points
    link.save()
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_header.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def exam_create(request):
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error.", status=403)
    current_tenant = membership.tenant

    if request.method == "POST":
        title = request.POST.get('title', 'Examen sin título').strip()
        exam = Exam.objects.create(tenant=current_tenant, author=request.user, title=title)
        redirect_url = reverse('backoffice:exam_constructor', args=[exam.id])
        return HttpResponse(headers={'HX-Redirect': redirect_url})

    return render(request, 'backoffice/partials/exam_form.html')

@login_required
@require_http_methods(["POST"])
def exam_delete(request, pk):
    try:
        exam = get_object_or_404(Exam, pk=pk, tenant__memberships__user=request.user)
        exam.delete()
        response = HttpResponse("", status=200)
        response['HX-Redirect'] = reverse('backoffice:dashboard')
        return response
    except Http404:
        return HttpResponse("No encontrado.", status=404)

@login_required
@require_http_methods(["POST"])
def item_delete(request, pk):
    try:
        item = get_object_or_404(Item, pk=pk, tenant__memberships__user=request.user)
        item.delete()
        response = HttpResponse("", status=200)
        response['HX-Redirect'] = reverse('backoffice:dashboard')
        return response
    except Http404:
        return HttpResponse("No encontrado.", status=404)


@login_required
@require_http_methods(["GET"])
def filter_items(request):
    try:
        memberships = TenantMembership.objects.filter(user=request.user)
        user_tenants = memberships.values_list('tenant', flat=True)
    except Exception:
        return HttpResponse("Error.", status=403)

    filter_type = request.GET.get('filter', 'all')
    base_query = Item.objects.filter(tenant__in=user_tenants)
    
    if filter_type == 'in_use':
        base_query = base_query.annotate(in_use_count=Count('exams')).filter(in_use_count__gt=0)
    elif filter_type == 'not_in_use':
        base_query = base_query.annotate(in_use_count=Count('exams')).filter(in_use_count=0)
    else:
        base_query = base_query.annotate(in_use_count=Count('exams'))

    item_list = base_query.annotate(
        exam_titles=StringAgg('exams__title', delimiter=', ', distinct=True)
    ).order_by('-created_at')

    context = {
        'item_list': item_list,
        'active_filter': filter_type, 
    }
    return render(request, 'backoffice/partials/_bank_panel.html', context)


@login_required
def item_detail_view(request, item_id):
    try:
        item = get_object_or_404(Item, id=item_id, tenant__memberships__user=request.user)
        options = item.options if isinstance(item.options, list) else []
        return render(request, 'backoffice/partials/item_detail_modal_content.html', {
            'item': item,
            'options': options
        })
    except Exception as e:
        return HttpResponse(f"<div class='text-red-500'>Error cargando detalle: {e}")


# --- IA: FLUJO DE CURADURÍA (Preview + Commit) ---

@login_required
@require_http_methods(["POST"])
def ai_preview_items(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    user_prompt = request.POST.get('ai_prompt', '').strip()
    
    if not user_prompt:
        return HttpResponse(status=204)

    try:
        existing_stems = Item.objects.filter(
            tenant=exam.tenant,
            stem__icontains=user_prompt
        ).values_list('stem', flat=True)[:20]

        avoid_text = ""
        if existing_stems:
            lista_preguntas = "\n- ".join(existing_stems)
            avoid_text = f"\nIMPORTANTE - YA TENGO ESTAS PREGUNTAS, NO LAS REPITAS:\n{lista_preguntas}\n"

        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        prompt = (
            "Eres un experto en evaluación académica universitaria.\n"
            f"PEDIDO: \"{user_prompt}\".\n"
            "INSTRUCCIONES:\n"
            "1. Genera preguntas de opción múltiple según el pedido (Máx 10).\n"
            "2. Si no pide cantidad, genera 5.\n"
            "3. INCLUYE ETIQUETAS: Para cada pregunta, genera un string con 2 o 3 etiquetas clave separadas por comas (ej: 'Historia, Europa, Guerra') en el campo 'tags'.\n"
            f"{avoid_text}"
            "\n"
            "--- FORMATO JSON ---\n"
            "Devuelve SOLO un JSON Array válido:\n"
            "[{\"stem\": \"...\", \"correct_answer\": \"...\", \"distractors\": [\"...\", \"...\"], \"tags\": \"tag1, tag2\"}]"
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        
        generated_data = json.loads(response.text)
        
        # --- PREPARACIÓN PARA HTML ---
        for item in generated_data:
            # Empaquetamos el JSON como string para que no se rompa en el template
            item['json_string'] = json.dumps(item)
        
        return render(request, 'backoffice/partials/_ai_curation_modal.html', {
            'exam': exam,
            'generated_items': generated_data,
            'user_prompt': user_prompt
        })

    except Exception as e:
        return HttpResponse(f"<div class='bg-red-100 text-red-700 p-4 rounded mb-4'>Error IA: {e}</div>")


@login_required
@require_http_methods(["POST"])
def ai_commit_items(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    
    # 1. Lista completa (Banco)
    items_all_json = request.POST.getlist('items_all')
    
    # 2. Lista seleccionada (Examen)
    items_selected_json = set(request.POST.getlist('items_selected'))
    
    saved_count = 0
    added_to_exam_count = 0
    
    for item_json in items_all_json:
        try:
            # --- CORRECCIÓN: Limpieza y Parseo Seguro ---
            clean_json = item_json.replace('\n', ' ').replace('\r', '')
            data = json.loads(clean_json)
            # --------------------------------------------
            
            options_list = [{"text": data['correct_answer'], "correct": True}]
            for dist in data.get('distractors', []):
                options_list.append({"text": dist, "correct": False})
            
            # A. Guardar en Banco (con tags si vienen)
            item, created = Item.objects.get_or_create(
                tenant=exam.tenant,
                stem__iexact=data['stem'].strip(),
                defaults={
                    'author': request.user,
                    'item_type': 'MC',
                    'stem': data['stem'].strip(),
                    'difficulty': 2,
                    'options': options_list,
                    'tags': data.get('tags', ['IA-Gen']) # Guardamos tags si existen
                }
            )
            saved_count += 1
            
            # B. Guardar en Examen (si estaba seleccionado)
            # Comparamos el string original para asegurar coincidencia exacta
            # Nota: en production, usar un ID temporal sería más robusto, pero esto funciona para el MVP.
            if item_json in items_selected_json:
                ExamItemLink.objects.get_or_create(exam=exam, item=item)
                added_to_exam_count += 1
            
        except Exception as e:
            print(f"Error guardando item IA: {e}")
            continue

    if saved_count > 0:
        msg = f"Proceso finalizado: {saved_count} guardadas en Banco."
        if added_to_exam_count > 0:
            msg = f"¡Listo! {added_to_exam_count} agregadas al Examen (y {saved_count} guardadas en Banco)."
        messages.success(request, msg)
    else:
        messages.warning(request, "No se procesó ninguna pregunta.")

    context = _get_constructor_context(request, exam_id)
    response = render(request, 'backoffice/partials/_constructor_oob_update.html', context)
    response['HX-Trigger'] = 'closeAiModal' 
    return response


# --- PUBLICACIÓN ---
@login_required
@require_http_methods(["POST"])
def exam_publish(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    total_points = ExamItemLink.objects.filter(exam=exam).aggregate(Sum('points'))['points__sum'] or 0.0

    try:
        if exam.status == 'draft':
            if not exam.items.exists():
                messages.error(request, "No puedes publicar un examen sin preguntas.")
            else:
                exam.status = "published" 
                exam.published_at = timezone.now()
                exam.save()
                
                if total_points != 10.0:
                    messages.warning(request, f"Examen publicado. Total: {total_points} (Ideal: 10).")
                else:
                    messages.success(request, "¡Examen publicado correctamente!")
        else:
            messages.info(request, "Este examen ya estaba publicado.")

    except Exception as e:
        messages.error(request, f"Error interno: {e}")
        context = { 'exam': exam, 'total_points': total_points }
        return render(request, 'backoffice/partials/_constructor_header.html', context, status=500)

    context = { 'exam': exam, 'total_points': total_points }
    return render(request, 'backoffice/partials/_constructor_header.html', context)


@login_required
@require_http_methods(["POST"])
def exam_unpublish(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    total_points = ExamItemLink.objects.filter(exam=exam).aggregate(Sum('points'))['points__sum'] or 0.0
    
    try:
        if exam.status == 'published':
            exam.status = "draft"
            exam.published_at = None
            exam.save()
            messages.warning(request, "Examen revertido a Borrador.")
        else:
            messages.info(request, "Este examen ya era un borrador.")

    except Exception as e:
        messages.error(request, f"Error interno: {e}")
        context = { 'exam': exam, 'total_points': total_points }
        return render(request, 'backoffice/partials/_constructor_header.html', context, status=500)

    context = { 'exam': exam, 'total_points': total_points }
    return render(request, 'backoffice/partials/_constructor_header.html', context)
