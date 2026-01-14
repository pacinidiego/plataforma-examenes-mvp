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

# ==========================================
# SECCIÓN ALUMNO
# ==========================================

# 1. LOBBY (MODIFICADO: REDIRECCIÓN SI YA TERMINÓ)
def lobby_view(request, access_code):
    exam = get_object_or_404(Exam, access_code=access_code)
    
    if request.method == "POST":
        nombre = request.POST.get('full_name', '').strip()
        legajo = request.POST.get('student_id', '').strip()
        
        # Buscamos si ya tiene un intento finalizado
        finished_attempt = Attempt.objects.filter(
            exam=exam, student_legajo__iexact=legajo, completed_at__isnull=False
        ).first()

        if finished_attempt:
            # CAMBIO PRINCIPAL: Si ya terminó, lo mandamos a ver su nota directamente
            return redirect('runner:exam_finished', attempt_id=finished_attempt.id)
            
        # Buscamos si tiene un intento activo (sin terminar)
        active_attempt = Attempt.objects.filter(
            exam=exam, student_legajo__iexact=legajo, completed_at__isnull=True
        ).first()

        if active_attempt:
            active_attempt.student_name = nombre
            active_attempt.save()
            return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=active_attempt.id)

        # Si es nuevo, creamos el intento
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
            attempt.reference_face_url = data['reference_face']
            
        if 'dni_image' in data:
            attempt.photo_id_url = data['dni_image']
            
        attempt.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 5. VALIDACIÓN DNI
@require_POST
def validate_dni_ocr(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    # --- 1. CONFIGURACIÓN ---
    MAX_INTENTOS = 3
    intentos_previos = Evidence.objects.filter(attempt=attempt).count()
    intento_actual = intentos_previos + 1
    
    # --- 2. OBTENER Y SUBIR IMAGEN ---
    try:
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
        return JsonResponse({'success': False, 'message': f'Error imagen: {str(e)}'})

    # --- 3. VALIDACIÓN IA ---
    if not GOOGLE_API_KEY:
        return JsonResponse({'success': True, 'message': 'Simulación (Sin API Key).'})

    # PRIORIDAD DE MODELOS
    modelos_a_probar = ["gemini-flash-lite-latest", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
    
    ia_success = False
    error_actual = ""
    modelo_usado = ""
    force_manual_review = False 

    payload = {
        "contents": [{
            "parts": [
                { "text": "Analiza esta imagen. Responde SOLO JSON: {\"es_documento\": true, \"numeros\": \"123456\"}. Si no es DNI, false. No uses markdown." },
                { "inline_data": { "mime_type": "image/jpeg", "data": base64_clean } }
            ]
        }]
    }
    headers = {'Content-Type': 'application/json'}

    # Bucle para probar modelos
    for model_name in modelos_a_probar:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        try:
            print(f"--- Intentando validar con modelo: {model_name} ---")
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
            
            elif response.status_code == 404:
                error_actual = f"Modelo {model_name} no encontrado (404)"
                continue 
            
            elif response.status_code == 429:
                error_actual = f"Cuota excedida en {model_name} (429)."
                if model_name == modelos_a_probar[-1]:
                     force_manual_review = True
                continue
            
            else:
                error_actual = f"Error API ({response.status_code})"
                break 

        except Exception as e:
            error_actual = f"Error red: {str(e)}"
            break

    # --- 4. RESULTADO FINAL ---
    if ia_success:
        last_ev = Evidence.objects.filter(attempt=attempt).last()
        if last_ev:
            last_ev.gemini_analysis = {'status': 'success', 'modelo': modelo_usado}
            last_ev.save()
        return JsonResponse({'success': True, 'message': 'Identidad verificada.'})
    
    else:
        try:
            AttemptEvent.objects.create(
                attempt=attempt, event_type='IDENTITY_MISMATCH', 
                metadata={'reason': f'Fallo ({intento_actual}): {error_actual}'}
            )
        except: pass

        if intento_actual >= MAX_INTENTOS or force_manual_review:
            last_ev = Evidence.objects.filter(attempt=attempt).last()
            if last_ev:
                last_ev.gemini_analysis = {'status': 'manual_review', 'error': error_actual}
                last_ev.save()
            
            return JsonResponse({
                'success': True, 
                'warning': True,
                'message': 'Pase a revisión manual.', 
                'retry': False
            })
        else:
            return JsonResponse({
                'success': False, 
                'message': f'Fallo: {error_actual}. Reintentando...', 
                'retry': True
            })

# 6. RUNNER (Examen)
def exam_runner_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

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

    if remaining <= 0 and attempt.start_time:
        return redirect('runner:submit_exam', attempt_id=attempt.id)

    items = list(exam.items.all())
    if exam.shuffle_items:
        random.Random(str(attempt.id)).shuffle(items)
    
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

# API: INICIAR TIMER
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
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error'}, status=400)

# 8. FINALIZAR (NORMALIZADO A ESCALA DE 10)
def submit_exam_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    exam = attempt.exam
    
    score_obtained = 0
    total_possible_points = 0
    
    questions = exam.items.all()
    answers = attempt.answers or {}

    for q in questions:
        # Calcular puntos posibles
        link = exam.examitemlink_set.filter(item=q).first()
        points_for_question = link.points if link else 1.0
        total_possible_points += points_for_question

        # Calcular puntos obtenidos
        selected = answers.get(str(q.id))
        if selected:
            correct = next((o for o in (q.options or []) if o.get('correct')), None)
            if correct and correct.get('text') == selected:
                score_obtained += points_for_question

    # Normalizar a escala de 10
    if total_possible_points > 0:
        final_grade = (score_obtained / total_possible_points) * 10
    else:
        final_grade = 0.0

    attempt.score = final_grade
    attempt.completed_at = timezone.now()
    attempt.save()
    
    return redirect('runner:exam_finished', attempt_id=attempt.id)

# 9. PANTALLA FINAL (MODIFICADO: CON CÁLCULO DE DETALLES)
# 9. PANTALLA FINAL (CON FILTRO DE SEGURIDAD/RIESGO)
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    # --- 1. CALCULAR RIESGO (Misma lógica que el Dashboard) ---
    events = attempt.events.all()
    risk_score = 0
    risk_score += events.filter(event_type='FOCUS_LOST').count() * 1
    risk_score += events.filter(event_type='FULLSCREEN_EXIT').count() * 2
    risk_score += events.filter(event_type='NO_FACE').count() * 3
    risk_score += events.filter(event_type='MULTI_FACE').count() * 5
    risk_score += events.filter(event_type='IDENTITY_MISMATCH').count() * 10
    
    # Obtenemos el límite de riesgo alto configurado en el tenant
    limit_high = attempt.exam.tenant.risk_threshold_high
    
    # Determinamos si debe ir a revisión
    # Si supera el riesgo O si ya estaba marcado manualmente como 'requires_review' (si tu modelo lo tiene)
    en_revision = risk_score > limit_high

    # Si está en revisión, NO calculamos detalles ni mostramos nota
    if en_revision:
        return render(request, 'runner/finished.html', {
            'attempt': attempt,
            'en_revision': True,  # <--- Bandera clave para el HTML
            'risk_score': risk_score # Opcional, por si quieres debuggear
        })

    # --- 2. SI ES SEGURO: CALCULAR NOTA Y DETALLES ---
    items = attempt.exam.items.all()
    student_answers = attempt.answers or {}
    
    detalles = []
    
    for item in items:
        user_response = student_answers.get(str(item.id))
        correct_option = next((o for o in (item.options or []) if o.get('correct')), None)
        correct_text = correct_option.get('text') if correct_option else None
        
        es_correcta = False
        if user_response and correct_text and user_response == correct_text:
            es_correcta = True
            
        detalles.append({
            'es_correcta': es_correcta,
            'pregunta_id': item.id
        })

    score_percentage = 0
    if attempt.score is not None:
        score_percentage = int((attempt.score / 10) * 100)

    return render(request, 'runner/finished.html', {
        'attempt': attempt,
        'detalles': detalles,
        'score_percentage': score_percentage,
        'en_revision': False
    })

# 10. LOGS
# Busca la función # 10. LOGS y reemplázala con esta versión:

@require_POST
def log_event(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        
        # Parseamos los datos que vienen del navegador
        data = json.loads(request.body)
        event_type = data.get('event_type')
        metadata = data.get('metadata', {})
        
        # --- NUEVO: MANEJO DE IMAGEN DE INCIDENTE ---
        image_data = data.get('image', None) 

        evidence_url = None # Por defecto no hay foto

        if image_data:
            # 1. Limpiamos el base64 (quitamos el encabezado 'data:image/jpeg;base64,')
            if ';base64,' in image_data:
                base64_clean = image_data.split(';base64,')[1]
            else:
                base64_clean = image_data
            
            # 2. Convertimos texto a archivo en memoria
            image_content = base64.b64decode(base64_clean)
            
            # 3. Definimos nombre (INCIDENTE_ + ID + Aleatorio)
            filename = f"evidence/INCIDENTE_{attempt.id}_{uuid.uuid4().hex[:6]}.jpg"
            
            # 4. ¡AQUÍ OCURRE LA MAGIA! 
            # default_storage.save sube el archivo a Cloudflare R2
            saved_path = default_storage.save(filename, ContentFile(image_content))
            
            # 5. Obtenemos la URL pública de Cloudflare
            evidence_url = default_storage.url(saved_path)

            # 6. Creamos el registro en la tabla Evidence (apuntando a la URL)
            Evidence.objects.create(
                attempt=attempt,
                file_url=evidence_url, # <--- Guardamos solo el LINK
                timestamp=timezone.now(),
                gemini_analysis={
                    'tipo': 'INCIDENTE', 
                    'motivo': event_type, 
                    'alerta': 'ALTA'
                }
            )
            
            # Agregamos la URL al log de texto también por si acaso
            metadata['evidence_url'] = evidence_url

        # Guardamos el evento de log normal
        AttemptEvent.objects.create(
            attempt=attempt, 
            event_type=event_type, 
            metadata=metadata
        )
        
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 11-15. GESTIÓN DOCENTE
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
        risk_score += events.filter(event_type='IDENTITY_MISMATCH').count() * 10
        
        status_color = 'green'
        status_text = "Confiable"
        
        if risk_score > limit_high: 
            status_color = 'red'
            status_text = "Alto Riesgo"
        elif risk_score > limit_medium: 
            status_color = 'yellow'
            status_text = "Riesgo Medio"
        
        # MOSTRAR NOTA SI EL RIESGO ES BAJO (VERDE)
        show_grade = (status_color == 'green')

        results.append({
            'attempt': attempt, 
            'risk_score': risk_score,
            'status_color': status_color, 
            'status_text': status_text,
            'event_count': events.count(),
            'show_grade': show_grade
        })
    return render(request, 'runner/teacher_dashboard.html', {'exam': exam, 'results': results})

# 12. DETALLE DEL INTENTO (CON RESPUESTAS)
@login_required
@user_passes_test(is_staff)
def attempt_detail_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    events = attempt.events.all().order_by('timestamp')
    evidence_list = Evidence.objects.filter(attempt=attempt).order_by('timestamp')
    
    items = attempt.exam.items.all()
    student_answers = attempt.answers or {}
    
    qa_list = []
    for item in items:
        user_response = student_answers.get(str(item.id))
        correct_option = next((o for o in (item.options or []) if o.get('correct')), None)
        correct_text = correct_option.get('text') if correct_option else "N/A"
        
        is_correct = False
        if user_response and user_response == correct_text:
            is_correct = True
            
        qa_list.append({
            'question': item.stem,
            'user_response': user_response,
            'correct_response': correct_text,
            'is_correct': is_correct
        })

    return render(request, 'runner/attempt_detail.html', {
        'attempt': attempt, 
        'events': events, 
        'evidence_list': evidence_list,
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
