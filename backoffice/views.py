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
from django.db.models import Count, Q
from django.contrib import messages 
from django.utils import timezone 
# [CORRECCIÓN] Import de StringAgg en la ubicación correcta
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
            return HttpResponse("Error: No tiene un tenant asignado.", status: 403)
            
    except Exception:
        return HttpResponse("Error: No se pudo verificar la membresía del tenant.", status: 500)

    exam_list = Exam.objects.filter(tenant__in=user_tenants).order_by('-created_at')[:20]
    
    item_list = Item.objects.filter(tenant__in=user_tenants)\
                            .annotate(
                                in_use_count=Count('exams'),
                                exam_titles=StringAgg('exams__title', delimiter=', ', distinct=True) # <-- Para el tooltip
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

# --- VISTAS DE CONSTRUCTOR DE ÍTEMS (S1c) ---
@login_required
@require_http_methods(["GET", "POST"])
def item_create(request):
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status: 403)
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
                return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe una pregunta con ese enunciado exacto.</div>")

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
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error: Usuario no tiene un tenant asignado.", status: 403)
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
            return HttpResponse(f"<div class='p-4 bg-red-800 text-red-100 rounded-lg'><strong>Error:</strong> Ya existe OTRA pregunta con ese enunciado.</div>")

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
    return HttpResponse("Desactivado.", status: 403)

@login_required
def poll_task_status_view(request, task_id):
    return HttpResponse("Desactivado.", status: 403)

@login_required
def download_excel_template_view(request):
    return HttpResponse("Desactivado.", status: 403)


# --- CONSTRUCTOR DE EXÁMENES ---

def _get_constructor_context(request, exam_id, highlight_map=None):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    current_tenant = exam.tenant
    
    exam_items = exam.items.all().order_by('examitemlink__order')

    bank_items = Item.objects.filter(tenant=current_tenant)\
                             .exclude(id__in=exam_items.values_list('id', flat=True))\
                             .order_by('-created_at')
    
    if highlight_map:
        for item in bank_items:
            item.source_tag = highlight_map.get(item.id, None)
                             
    return {
        'exam': exam,
        'exam_items': exam_items,
        'bank_items': bank_items,
        'exam_items_count': exam_items.count(),
        'bank_items_count': bank_items.count(),
    }

@login_required
def exam_constructor_view(request, exam_id):
    try:
        context = _get_constructor_context(request, exam_id)
        return render(request, 'backoffice/constructor.html', context)
    except Http404:
        return HttpResponse("Examen no encontrado.", status: 404)
    except Exception as e:
        return HttpResponse(f"Error: {e}", status: 500)

@login_required
@require_http_methods(["POST"])
def add_item_to_exam(request, exam_id, item_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    item = get_object_or_404(Item, id=item_id, tenant=exam.tenant)
    ExamItemLink.objects.get_or_create(exam=exam, item=item)
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_body.html', context)

@login_required
@require_http_methods(["POST"])
def remove_item_from_exam(request, exam_id, item_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    ExamItemLink.objects.filter(exam=exam, item_id=item_id).delete()
    context = _get_constructor_context(request, exam_id)
    return render(request, 'backoffice/partials/_constructor_body.html', context)

@login_required
@require_http_methods(["GET", "POST"])
def exam_create(request):
    membership = TenantMembership.objects.filter(user=request.user).first()
    if not membership:
        return HttpResponse("Error.", status: 403)
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
        response = HttpResponse("", status: 200)
        response['HX-Redirect'] = reverse('backoffice:dashboard')
        return response
    except Http404:
        return HttpResponse("No encontrado.", status: 404)

@login_required
@require_http_methods(["POST"])
def item_delete(request, pk):
    try:
        item = get_object_or_404(Item, pk=pk, tenant__memberships__user=request.user)
        item.delete()
        response = HttpResponse("", status: 200)
        response['HX-Redirect'] = reverse('backoffice:dashboard')
        return response
    except Http404:
        return HttpResponse("No encontrado.", status: 404)


@login_required
@require_http_methods(["GET"])
def filter_items(request):
    try:
        memberships = TenantMembership.objects.filter(user=request.user)
        user_tenants = memberships.values_list('tenant', flat=True)
    except Exception:
        return HttpResponse("Error.", status: 403)

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
        return HttpResponse(f"<div class='text-red-500'>Error cargando detalle: {e}</div>")


@login_required
@require_http_methods(["POST"])
def ai_suggest_items(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    user_prompt = request.POST.get('ai_prompt')
    
    if not user_prompt:
        messages.warning(request, "Escribe un tema para generar preguntas.")
        context = _get_constructor_context(request, exam_id)
        return render(request, 'backoffice/partials/_constructor_body.html', context)

    highlight_map = {} 
    gen_count = 0
    found_count = 0 

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        prompt = (
            "Eres un experto en evaluación académica.\n"
            f"El usuario necesita preguntas sobre: \"{user_prompt}\".\n"
            "1. Genera 3 preguntas NUEVAS de opción múltiple sobre este tema.\n"
            "2. Asegúrate de que sean preguntas de calidad universitaria.\n"
            "\n"
            "--- FORMATO DE SALIDA ---\n"
            "Devuelve ÚNICAMENTE un JSON Array válido:\n"
            "[{\"stem\": \"...\", \"correct_answer\": \"...\", \"distractors\": [\"...\", \"...\", \"...\"]}]"
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        
        generated_data = json.loads(response.text)
        
        if generated_data:
            for data in generated_data:
                options_list = [{"text": data['correct_answer'], "correct": True}]
                for dist in data.get('distractors', []):
                    options_list.append({"text": dist, "correct": False})
                
                item, created = Item.objects.get_or_create(
                    tenant=exam.tenant,
                    stem__iexact=data['stem'].strip(),
                    defaults={
                        'author': request.user,
                        'item_type': 'MC',
                        'stem': data['stem'].strip(),
                        'difficulty': 2, 
                        'options': options_list,
                        'tags': ['IA-Gen'] 
                    }
                )
                
                tag = 'generated' if created else 'found'
                highlight_map[item.id] = tag
                if created:
                    gen_count += 1

        existing_matches = Item.objects.filter(
            tenant=exam.tenant,
            stem__icontains=user_prompt 
        ).exclude(id__in=exam.items.values_list('id', flat=True))[:5]

        for item in existing_matches:
            if item.id not in highlight_map:
                highlight_map[item.id] = 'found'
                found_count += 1 

        if gen_count > 0:
            messages.success(request, f"Se generaron {gen_count} preguntas nuevas en el BANCO (columna derecha).")
        elif found_count > 0:
            messages.info(request, f"Se encontraron {found_count} preguntas existentes relacionadas en tu banco.")
        else:
            messages.warning(request, "No se generaron preguntas nuevas (posible duplicado o error IA).")

    except Exception as e:
        messages.error(request, f"Error procesando la solicitud: {e}")

    updated_context = _get_constructor_context(request, exam_id, highlight_map=highlight_map)
    return render(request, 'backoffice/partials/_constructor_body.html', updated_context)


@login_required
@require_http_methods(["POST"])
def exam_publish(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    
    try:
        if exam.status == 'draft':
            if not exam.items.exists():
                messages.error(request, "No puedes publicar un examen sin preguntas.")
            else:
                exam.status = "published" 
                exam.published_at = timezone.now()
                exam.save()
                messages.success(request, "¡Examen publicado! Ahora puedes compartir el enlace.")
        else:
            messages.info(request, "Este examen ya estaba publicado.")

    except Exception as e:
        messages.error(request, f"Error interno al publicar: {e}")
        context = { 'exam': exam }
        return render(request, 'backoffice/partials/_constructor_header.html', context, status: 500)

    context = { 'exam': exam }
    return render(request, 'backoffice/partials/_constructor_header.html', context)


@login_required
@require_http_methods(["POST"])
def exam_unpublish(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, tenant__memberships__user=request.user)
    
    try:
        if exam.status == 'published':
            exam.status = "draft"
            exam.published_at = None
            exam.save()
            messages.warning(request, "Se anuló la publicación. El examen vuelve a ser un borrador.")
        else:
            messages.info(request, "Este examen ya era un borrador.")

    except Exception as e:
        messages.error(request, f"Error interno al anular la publicación: {e}")
        context = { 'exam': exam }
        return render(request, 'backoffice/partials/_constructor_header.html', context, status: 500)

    context = { 'exam': exam }
    return render(request, 'backoffice/partials/_constructor_header.html', context)
