import random
import json
import base64
import re
import os
import traceback
import requests
import time
import uuid
from io import BytesIO
from PIL import Image

# Django Imports
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

# Librerías Externas
from weasyprint import HTML
import google.generativeai as genai 

# Modelos
from exams.models import Exam
from .models import Attempt, AttemptEvent, Evidence

# --- CONFIGURACIÓN GEMINI ---
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
    except:
        pass

# --- FUNCIONES AUXILIARES ---
def is_staff(user):
    return user.is_staff

def es_docente_o_admin(user):
    return user.is_staff or user.groups.filter(name='Docente').exists()

# --- CÁLCULO DE NOTA CENTRALIZADO ---
def calculate_final_score(attempt):
    """
    Calcula la nota considerando:
    1. Respuestas correctas.
    2. Preguntas anuladas (valen 0 si están en penalized_items).
    3. Penalidad manual (penalty_points).
    """
    exam = attempt.exam
    score_obtained = 0
    total_possible_points = 0
    questions = exam.items.all()
    answers = attempt.answers or {}
    # Convertimos a strings para asegurar coincidencia con los IDs del template
    penalized = [str(x) for x in (attempt.penalized_items or [])]

    for q in questions:
        link = exam.examitemlink_set.filter(item=q).first()
        points_for_question = link.points if link else 1.0
        total_possible_points += points_for_question
        
        # Si la pregunta está anulada por el docente, suma 0 puntos
        if str(q.id) in penalized:
            continue 

        selected = answers.get(str(q.id))
        if selected:
            correct = next((o for o in (q.options or []) if o.get('correct')), None)
            if correct and correct.get('text') == selected:
                score_obtained += points_for_question

    final_score = 0.0
    if total_possible_points > 0: 
        final_score = (score_obtained / total_possible_points) * 10
    
    # Restar la penalidad manual (si existe)
    final_score -= (attempt.penalty_points or 0.0)
    
    return max(0.0, final_score)

# ==========================================
# SECCIÓN ALUMNO
# ==========================================

# 1. LOBBY
def lobby_view(request, access_code):
    exam = get_object_or_404(Exam, access_code=access_code)
    
    if request.method == "POST":
        nombre = request.POST.get('full_name', '').strip()
        legajo = request.POST.get('student_id', '').strip()
        
        finished_attempt = Attempt.objects.filter(
            exam=exam, student_legajo__iexact=legajo, completed_at__isnull=False
        ).first()

        if finished_attempt:
            return redirect('runner:exam_finished', attempt_id=finished_attempt.id)
            
        active_attempt = Attempt.objects.filter(
            exam=exam, student_legajo__iexact=legajo, completed_at__isnull=True
        ).first()

        if active_attempt:
            active_attempt.student_name = nombre
            active_attempt.save()
            return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=active_attempt.id)

        attempt = Attempt.objects.create(
            exam=exam, student_name=nombre, student_legajo=legajo,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=attempt.id)
        
    return render(request, 'runner/lobby.html', {'exam': exam})

# 2. TECH CHECK
def tech_check_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/tech_check.html', {'exam': exam, 'attempt': attempt})

# 3. BIOMETRIC GATE
def biometric_gate_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return redirect('runner:exam_runner', access_code=access_code, attempt_id=attempt.id)

# 4. REGISTRO BIOMÉTRICO
@require_POST
def register_biometrics(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        
        if 'reference_face' in data:
            image_data = data['reference_face']
            if image_data:
                if ';base64,' in image_data:
                    base64_clean = image_data.split(';base64,')[1]
                else:
                    base64_clean = image_data
                
                try:
                    image_content = base64.b64decode(base64_clean)
                    filename = f"evidence/FACE_REF_{attempt.id}_{uuid.uuid4().hex[:6]}.jpg"
                    saved_path = default_storage.save(filename, ContentFile(image_content))
                    file_url = default_storage.url(saved_path)
                    attempt.reference_face_url = file_url
                except Exception as e:
                    print(f"Error subiendo referencia facial: {e}")

        if 'dni_image' in data:
             image_data = data['dni_image']
             if image_data:
                if ';base64,' in image_data:
                    base64_clean = image_data.split(';base64,')[1]
                else:
                    base64_clean = image_data
                
                try:
                    image_content = base64.b64decode(base64_clean)
                    filename = f"evidence/DNI_REF_{attempt.id}_{uuid.uuid4().hex[:6]}.jpg"
                    saved_path = default_storage.save(filename, ContentFile(image_content))
                    file_url = default_storage.url(saved_path)
                    attempt.photo_id_url = file_url
                except Exception as e:
                    print(f"Error subiendo referencia DNI: {e}")
            
        attempt.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 5. VALIDACIÓN DNI
@require_POST
def validate_dni_ocr(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        
        intentos_previos = Evidence.objects.filter(attempt=attempt).exclude(file_url__contains='INCIDENTE').count()
        intento_actual = intentos_previos + 1
        
        data = json.loads(request.body)
        image_data = data.get('image', '')
        
        if ';base64,' in image_data:
            base64_clean = image_data.split(';base64,')[1]
        else:
            base64_clean = image_data
            
        if not base64_clean:
            return JsonResponse({'success': False, 'message': 'Imagen vacía.'})
        
        image_content = base64.b64decode(base64_clean)
        file_name = f"evidence/dni_{attempt.id}_intento_{intento_actual}_{uuid.uuid4().hex[:8]}.jpg"
        
        saved_path = default_storage.save(file_name, ContentFile(image_content))
        file_url = default_storage.url(saved_path)
        
        attempt.photo_id_url = file_url
        attempt.save()

        Evidence.objects.create(
            attempt=attempt,
            file_url=file_url,
            timestamp=timezone.now(),
            gemini_analysis={'intento': intento_actual, 'status': 'procesando'}
        )

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error interno: {str(e)}'})

    if not GOOGLE_API_KEY:
        return JsonResponse({'success': True, 'message': 'Simulación (Sin API Key).'})

    modelos_a_probar = ["gemini-flash-lite-latest", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    ia_success = False
    error_actual = ""
    modelo_usado = ""
    force_manual_review = False 
    MAX_INTENTOS = 3

    payload = {
        "contents": [{
            "parts": [
                { "text": "Analiza esta imagen. Responde SOLO JSON: {\"es_documento\": true, \"numeros\": \"123456\"}. Si no es DNI, false. No uses markdown." },
                { "inline_data": { "mime_type": "image/jpeg", "data": base64_clean } }
            ]
        }]
    }
    headers = {'Content-Type': 'application/json'}

    for model_name in modelos_a_probar:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                modelo_usado = model_name
                json_res = response.json()
                candidates = json_res.get('candidates', [])
                if not candidates:
                    error_actual = "IA bloqueó la imagen (Seguridad)"
                    break 
                
                raw_text = candidates[0].get('content', {}).get('parts', [])[0].get('text', '')
                clean_text = raw_text.replace('```json', '').replace('```', '').strip()
                ai_data = json.loads(clean_text)
                
                if ai_data.get('es_documento'):
                    numbers_found = str(ai_data.get('numeros', ''))
                    legajo_alumno = re.sub(r'[^0-9]', '', str(attempt.student_legajo))
                    if legajo_alumno and (legajo_alumno in numbers_found or numbers_found in legajo_alumno):
                        ia_success = True
                        error_actual = ""
                        break 
                    else:
                        error_actual = f"Legajo no coincide (Leído: {numbers_found})"
                        break 
                else:
                    error_actual = "No parece un DNI válido"
                    break 
            elif response.status_code == 404: continue 
            elif response.status_code == 429:
                if model_name == modelos_a_probar[-1]: force_manual_review = True
                continue
            else:
                error_actual = f"Error API ({response.status_code})"
                break 
        except Exception as e:
            error_actual = f"Error red: {str(e)}"
            break

    if ia_success:
        last_ev = Evidence.objects.filter(attempt=attempt).last()
        if last_ev:
            last_ev.gemini_analysis = {'status': 'success', 'modelo': modelo_usado, 'intento': intento_actual}
            last_ev.save()
        return JsonResponse({'success': True, 'message': 'Identidad verificada.'})
    
    else:
        # Genera Identity Mismatch pero con 'reason' para poder filtrarlo luego en logs
        try:
            AttemptEvent.objects.create(
                attempt=attempt, event_type='IDENTITY_MISMATCH', 
                metadata={'reason': f'Fallo ({intento_actual}): {error_actual}'}
            )
        except: pass

        if intento_actual >= MAX_INTENTOS or force_manual_review:
            last_ev = Evidence.objects.filter(attempt=attempt).last()
            if last_ev:
                last_ev.gemini_analysis = {'status': 'manual_review', 'error': error_actual, 'intento': intento_actual}
                last_ev.save()
            return JsonResponse({'success': True, 'warning': True, 'message': 'Pase a revisión manual.', 'retry': False})
        else:
            return JsonResponse({'success': False, 'message': f'Fallo: {error_actual}. Reintentando...', 'retry': True})

# 6. RUNNER
def exam_runner_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.completed_at: return redirect('runner:exam_finished', attempt_id=attempt.id)

    total_duration = exam.get_total_duration_seconds()
    if attempt.start_time:
        elapsed = (timezone.now() - attempt.start_time).total_seconds()
        remaining = max(0, total_duration - elapsed)
        saved_answers = attempt.answers or {}
        if remaining <= 0 and not saved_answers:
             attempt.start_time = timezone.now()
             attempt.save()
             remaining = total_duration
    else:
        remaining = total_duration

    if remaining <= 0 and attempt.start_time: return redirect('runner:submit_exam', attempt_id=attempt.id)

    items = list(exam.items.all())
    if exam.shuffle_items: random.Random(str(attempt.id)).shuffle(items)
    
    saved_answers = attempt.answers or {}
    initial_step = len(saved_answers)
    if initial_step >= len(items): initial_step = len(items) - 1

    return render(request, 'runner/exam_runner.html', {
        'exam': exam,
        'attempt': attempt,
        'items': items,
        'total_questions': len(items),
        'remaining_seconds': int(remaining),
        'time_per_item': exam.time_per_item,
        'initial_step': initial_step,
        'has_started': attempt.start_time is not None
    })

# API: TIMER
@require_POST
def start_exam_timer(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        if not attempt.start_time:
            attempt.start_time = timezone.now()
            attempt.save(update_fields=['start_time'])
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 7. GUARDAR RESPUESTA
@require_POST
def save_answer(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        if not attempt.start_time:
            attempt.start_time = timezone.now()
            attempt.save(update_fields=['start_time'])

        data = json.loads(request.body)
        current_answers = attempt.answers or {}
        current_answers[str(data.get('question_id'))] = data.get('answer')
        attempt.answers = current_answers
        attempt.save(update_fields=['answers', 'last_heartbeat']) 
        AttemptEvent.objects.create(attempt=attempt, event_type='ANSWER_SAVED', metadata={'qid': data.get('question_id')})
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error'}, status=400)

# 8. FINALIZAR
def submit_exam_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.completed_at: return redirect('runner:exam_finished', attempt_id=attempt.id)

    attempt.completed_at = timezone.now()
    # Usa la lógica centralizada para consistencia
    attempt.score = calculate_final_score(attempt)
    # Por defecto queda pendiente de revisión si hay riesgos, pero se guarda el score calculado
    if attempt.review_status == 'pending':
        # Podríamos añadir lógica auto-approve si risk es 0 aquí
        pass
        
    attempt.save()
    return redirect('runner:exam_finished', attempt_id=attempt.id)

# 9. PANTALLA FINAL
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    events = attempt.events.all()
    
    # Cálculo de Riesgo por Eventos
    risk_score = 0
    risk_score += events.filter(event_type='FOCUS_LOST').count() * 1
    risk_score += events.filter(event_type='FULLSCREEN_EXIT').count() * 2
    risk_score += events.filter(event_type='NO_FACE').count() * 3
    risk_score += events.filter(event_type='MULTI_FACE').count() * 5
    risk_score += events.filter(event_type='IDENTITY_MISMATCH').exclude(metadata__reason__startswith='Fallo').count() * 10
    
    limit_high = attempt.exam.tenant.risk_threshold_high
    
    # Verificar si la validación de DNI falló o quedó en manual
    last_dni_evidence = Evidence.objects.filter(attempt=attempt).exclude(file_url__contains='INCIDENTE').last()
    dni_manual_review = False
    if last_dni_evidence:
        status = last_dni_evidence.gemini_analysis.get('status', '')
        if status in ['manual_review', 'failed', 'error']:
            dni_manual_review = True

    # --- LÓGICA DE VISIBILIDAD DE NOTA ---
    # Approved: Muestra nota. Rejected: Muestra 0. Pending/Revision: Oculta.
    if attempt.review_status == 'approved':
        en_revision = False
    elif attempt.review_status == 'rejected':
        en_revision = False 
    else:
        # Si no hay decisión explícita, usamos la heurística de riesgo para ocultar
        en_revision = (risk_score > limit_high) or dni_manual_review

    if en_revision:
        return render(request, 'runner/finished.html', {'attempt': attempt, 'en_revision': True, 'risk_score': risk_score})

    items = attempt.exam.items.all()
    student_answers = attempt.answers or {}
    detalles = []
    
    for item in items:
        user_response = student_answers.get(str(item.id))
        correct_option = next((o for o in (item.options or []) if o.get('correct')), None)
        correct_text = correct_option.get('text') if correct_option else None
        es_correcta = False
        if user_response and correct_text and user_response == correct_text: es_correcta = True
        detalles.append({'es_correcta': es_correcta, 'pregunta_id': item.id})

    score_percentage = 0
    if attempt.score is not None: score_percentage = int((attempt.score / 10) * 100)

    return render(request, 'runner/finished.html', {
        'attempt': attempt, 'detalles': detalles, 'score_percentage': score_percentage, 'en_revision': False
    })

# 10. LOGS
@require_POST
def log_event(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        event_type = data.get('event_type')
        metadata = data.get('metadata', {})
        image_data = data.get('image', None) 
        evidence_url = None

        if image_data:
            if ';base64,' in image_data: base64_clean = image_data.split(';base64,')[1]
            else: base64_clean = image_data
            
            image_content = base64.b64decode(base64_clean)
            filename = f"evidence/INCIDENTE_{attempt.id}_{uuid.uuid4().hex[:6]}.jpg"
            saved_path = default_storage.save(filename, ContentFile(image_content))
            evidence_url = default_storage.url(saved_path)

            Evidence.objects.create(
                attempt=attempt, file_url=evidence_url, timestamp=timezone.now(),
                gemini_analysis={'tipo': 'INCIDENTE', 'motivo': event_type, 'alerta': 'ALTA'}
            )
            metadata['evidence_url'] = evidence_url

        AttemptEvent.objects.create(attempt=attempt, event_type=event_type, metadata=metadata)
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 11. DASHBOARD DOCENTE
@login_required
@user_passes_test(is_staff)
def teacher_dashboard_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    attempts = Attempt.objects.filter(exam=exam).order_by('-start_time').prefetch_related('events')
    limit_medium = exam.tenant.risk_threshold_medium
    limit_high = exam.tenant.risk_threshold_high

    results = []
    for attempt in attempts:
        events = attempt.events.all()
        risk_score = 0
        risk_score += events.filter(event_type='FOCUS_LOST').count() * 1
        risk_score += events.filter(event_type='FULLSCREEN_EXIT').count() * 2
        risk_score += events.filter(event_type='NO_FACE').count() * 3
        risk_score += events.filter(event_type='MULTI_FACE').count() * 5
        # Filtramos los mismatch de DNI en el score visual
        risk_score += events.filter(event_type='IDENTITY_MISMATCH').exclude(metadata__reason__startswith='Fallo').count() * 10
        
        dni_failed = False
        last_dni = Evidence.objects.filter(attempt=attempt).exclude(file_url__contains='INCIDENTE').last()
        if last_dni and last_dni.gemini_analysis.get('status') in ['manual_review', 'failed', 'error']:
            dni_failed = True

        status_color = 'green'
        status_text = "Confiable"
        
        # 1. Evaluación automática de riesgo
        if risk_score > limit_high or dni_failed: 
            status_color = 'red'
            status_text = "Alto Riesgo / Rev. Manual"
        elif risk_score > limit_medium: 
            status_color = 'yellow'
            status_text = "Riesgo Medio"
        
        # 2. Sobreescritura por estado manual
        if attempt.review_status == 'approved':
            status_color = 'blue'
            status_text = "Validado"
        elif attempt.review_status == 'rejected':
            status_color = 'gray'
            status_text = "Anulado"
        elif attempt.review_status == 'revision': # <--- NUEVA CONDICIÓN
            status_color = 'indigo'
            status_text = "En Revisión (Guardado)"
        
        results.append({
            'attempt': attempt, 
            'risk_score': risk_score, 
            'status_color': status_color, 
            'status_text': status_text, 
            'event_count': events.count(), 
            # Permitimos ver la nota también si está en revisión (para control docente)
            'show_grade': (status_color in ['green', 'blue', 'indigo'])
        })
    return render(request, 'runner/teacher_dashboard.html', {'exam': exam, 'results': results})

# 12. DETALLE DEL INTENTO (MODIFICADO Y COMPLETADO)
@login_required
@user_passes_test(is_staff)
def attempt_detail_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    # --- PROCESAMIENTO POST (Guardado) ---
    if request.method == "POST":
        action = request.POST.get('action')
        feedback = request.POST.get('teacher_comment', '').strip()
        
        # 1. Capturamos la penalidad manual (Puntos directos a restar)
        try: 
            raw_penalty = float(request.POST.get('penalty_points', 0))
            attempt.penalty_points = max(0.0, raw_penalty)
        except: 
            pass

        # 2. Capturamos las preguntas marcadas para anular (array de strings IDs)
        penalized_ids = request.POST.getlist('penalized_item')
        attempt.penalized_items = penalized_ids 

        attempt.teacher_comment = feedback

        # 3. Recalcular nota usando la función centralizada
        if action in ['save_penalties', 'approve', 'save_comment']:
            attempt.score = calculate_final_score(attempt)
            
            if action == 'approve':
                attempt.review_status = 'approved'
            elif attempt.review_status == 'pending':
                # Si solo guarda, pasa a revisión
                attempt.review_status = 'revision'

        elif action == 'reject':
            attempt.review_status = 'rejected'
            attempt.score = 0.0
            
        attempt.save()
        return redirect('runner:attempt_detail', attempt_id=attempt.id)

    # --- PREPARACIÓN DE DATOS (LECTURA) ---
    if attempt.start_time:
        raw_events = list(attempt.events.filter(timestamp__gte=attempt.start_time).order_by('timestamp'))
    else:
        raw_events = list(attempt.events.all().order_by('timestamp'))

    final_events = []
    skip_ids = set()
    question_alerts = {} 

    for i, event in enumerate(raw_events):
        if event.id in skip_ids:
            continue
        
        # --- FILTRO 1: Focus Gained fuera ---
        if event.event_type == 'FOCUS_GAINED':
            continue

        # --- FILTRO 2: Logs de DNI fuera ---
        if event.event_type == 'IDENTITY_MISMATCH':
            reason = str(event.metadata.get('reason', ''))
            if reason.startswith('Fallo'):
                continue

        # Lógica de agrupación de Focus Loss
        if event.event_type in ['FOCUS_LOST', 'FULLSCREEN_EXIT']:
            for j in range(i + 1, len(raw_events)):
                next_ev = raw_events[j]
                
                if next_ev.event_type == 'FOCUS_GAINED':
                    delta = (next_ev.timestamp - event.timestamp).total_seconds()
                    event.duration_away = int(delta)
                    event.return_timestamp = next_ev.timestamp
                    
                    skip_ids.add(next_ev.id) # Marcamos para saltar
                    
                    # Detectar respuesta rápida
                    for k in range(j + 1, len(raw_events)):
                        future_ev = raw_events[k]
                        time_diff = (future_ev.timestamp - next_ev.timestamp).total_seconds()
                        if time_diff > 30: break 
                        
                        if future_ev.event_type == 'ANSWER_SAVED':
                            reaction = (future_ev.timestamp - next_ev.timestamp).total_seconds()
                            event.suspicious_answer = True
                            event.reaction_time = int(reaction)
                            
                            qid = future_ev.metadata.get('qid')
                            if qid:
                                question_alerts[str(qid)] = f"Respondió {int(reaction)}s después de incidente"
                            
                            skip_ids.add(future_ev.id)
                            break
                        if future_ev.event_type in ['FOCUS_LOST', 'FULLSCREEN_EXIT']:
                            break
                    break 

            if not getattr(event, 'duration_away', None) and i + 1 < len(raw_events):
                 delta = (raw_events[i+1].timestamp - event.timestamp).total_seconds()
                 event.duration_away = int(delta)
        
        final_events.append(event)

    evidence_all = Evidence.objects.filter(attempt=attempt).order_by('timestamp')
    evidence_validation = [ev for ev in evidence_all if "INCIDENTE" not in (ev.file_url or "")]

    items = attempt.exam.items.all()
    student_answers = attempt.answers or {}
    penalized_set = set(attempt.penalized_items or [])
    
    qa_list = []
    for item in items:
        sid = str(item.id)
        user_response = student_answers.get(sid)
        correct_option = next((o for o in (item.options or []) if o.get('correct')), None)
        correct_text = correct_option.get('text') if correct_option else "N/A"
        is_correct = (user_response and user_response == correct_text)
        
        qa_list.append({
            'id': item.id,
            'question': item.stem, 
            'user_response': user_response,
            'correct_response': correct_text, 
            'is_correct': is_correct,
            'is_penalized': sid in penalized_set,
            'alert': question_alerts.get(sid)
        })

    return render(request, 'runner/attempt_detail.html', {
        'attempt': attempt, 
        'events': final_events, 
        'evidence_list': evidence_validation, 
        'qa_list': qa_list
    })

@login_required
@user_passes_test(is_staff)
def teacher_home_view(request):
    exams = Exam.objects.all().order_by('-id') 
    return render(request, 'runner/teacher_home.html', {'exams': exams})

@login_required
@user_passes_test(is_staff)
def portal_docente_view(request):
    return render(request, 'runner/portal_docente.html')

@login_required
@user_passes_test(es_docente_o_admin)
def descargar_pdf_examen(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    try: cantidad_temas = int(request.GET.get('cantidad', 1))
    except: cantidad_temas = 1
    cantidad_temas = max(1, min(cantidad_temas, 10))
    pool_faciles = list(exam.items.filter(difficulty=1))
    pool_medias = list(exam.items.filter(difficulty=2))
    pool_dificiles = list(exam.items.filter(difficulty=3))
    examenes_generados = []
    for i in range(cantidad_temas):
        tema_label = chr(65 + i)
        seleccion = []
        seleccion += random.sample(pool_faciles, min(len(pool_faciles), len(pool_faciles)))
        seleccion += random.sample(pool_medias, min(len(pool_medias), len(pool_medias)))
        seleccion += random.sample(pool_dificiles, min(len(pool_dificiles), len(pool_dificiles)))
        random.shuffle(seleccion) 
        preguntas_data = []
        claves_tema = []
        for idx, item in enumerate(seleccion, 1):
            opciones = list(item.options or [])
            random.shuffle(opciones)
            letra_correcta = "?"
            for j, op in enumerate(opciones):
                op['letra'] = chr(65 + j)
                if op.get('correct'): letra_correcta = op['letra']
            claves_tema.append(f"{idx}-{letra_correcta}")
            preguntas_data.append({'id': item.id, 'texto': item.stem, 'opciones': opciones})
        examenes_generados.append({'tema': tema_label, 'preguntas': preguntas_data, 'claves': claves_tema})
    html_string = render_to_string('classroom_exams/pdf_variantes.html', {
        'config': {'nombre': exam.title, 'materia': 'Examen Generado'},
        'examenes_generados': examenes_generados,
    })
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
    filename = f"Examen_{exam.title.replace(' ', '_')}_{cantidad_temas}Temas.pdf"
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
