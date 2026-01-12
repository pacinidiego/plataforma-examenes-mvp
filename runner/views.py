import random
import json
import base64
import re
import os
import traceback
import requests
import time
import uuid  # <--- Nuevo import para nombres de archivo únicos
from io import BytesIO
from PIL import Image

# Django Imports
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.files.base import ContentFile # <--- Para convertir base64 a archivo
from django.core.files.storage import default_storage # <--- Para subir a Cloudflare

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
            return render(request, 'runner/lobby.html', {
                'exam': exam,
                'error': f'Acceso denegado. El alumno con legajo "{legajo}" ya envió este examen.'
            })
            
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
        
        # Nota: Aquí también podrías implementar la subida a Cloudflare si quisieras,
        # pero por ahora lo dejamos simple para no romper el flujo.
        if 'reference_face' in data:
            attempt.reference_face_url = data['reference_face']
            
        if 'dni_image' in data:
            attempt.photo_id_url = data['dni_image']
            
        attempt.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 5. VALIDACIÓN DNI (CON UPLOAD A CLOUDFLARE R2 ☁️)
@require_POST
def validate_dni_ocr(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    # --- A. OBTENER Y SUBIR IMAGEN ---
    try:
        data = json.loads(request.body)
        image_data = data.get('image', '')
        
        if ';base64,' in image_data:
            base64_clean = image_data.split(';base64,')[1]
        else:
            base64_clean = image_data
            
        if not base64_clean:
            return JsonResponse({'success': False, 'message': 'Imagen vacía.'})
        
        # 1. Decodificar la imagen en memoria
        image_content = base64.b64decode(base64_clean)
        
        # 2. Generar nombre único: evidence/{exam_id}/{attempt_id}_{random}.jpg
        file_name = f"evidence/dni_{attempt.id}_{uuid.uuid4().hex[:8]}.jpg"
        
        # 3. ¡SUBIR A CLOUDFLARE! (Esto usa tu configuración de settings.py)
        # default_storage.save devuelve el nombre con el que se guardó
        saved_path = default_storage.save(file_name, ContentFile(image_content))
        
        # 4. Obtener la URL pública (o firmada) del archivo
        file_url = default_storage.url(saved_path)
        
        # 5. Guardar el LINK en la base de datos (mucho más ligero)
        attempt.photo_id_url = file_url
        attempt.save()

    except Exception as e:
        print(f"Error subiendo imagen: {e}")
        return JsonResponse({'success': False, 'message': f'Error guardando imagen: {str(e)}'})

    if not GOOGLE_API_KEY:
        return JsonResponse({'success': True, 'message': 'Validación simulada (Sin API Key).'})

    # --- B. CONFIGURACIÓN IA ---
    model_name = "gemini-1.5-flash"
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GOOGLE_API_KEY}"
    
    # Enviamos el base64 a Gemini (Gemini necesita los bytes, no el link de Cloudflare)
    payload = {
        "contents": [{
            "parts": [
                { "text": "Analiza esta imagen. Responde SOLO JSON: {\"es_documento\": true, \"numeros\": \"123456\"}. Si no es DNI, false. No uses markdown." },
                { "inline_data": { "mime_type": "image/jpeg", "data": base64_clean } }
            ]
        }]
    }
    headers = {'Content-Type': 'application/json'}

    # --- C. BUCLE DE 3 INTENTOS ---
    ia_success = False
    
    for i in range(3):
        intento_num = i + 1
        error_actual = ""
        
        # Guardar Evidencia de este intento (Ahora con URL de Cloudflare)
        try:
            # Reusamos la URL de la imagen que ya subimos (es la misma foto)
            # O si cada intento fuera una foto distinta, tendríamos que subirla de nuevo.
            # Asumimos que es la misma foto del request.
            Evidence.objects.create(
                attempt=attempt,
                file_url=file_url, # <--- Guardamos el LINK de Cloudflare
                timestamp=timezone.now(),
                gemini_analysis={'intento': intento_num, 'status': 'procesando'}
            )
        except Exception:
            pass # Si falla guardar el log, seguimos

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                json_res = response.json()
                try:
                    candidates = json_res.get('candidates', [])
                    if not candidates:
                         error_actual = "IA bloqueó la imagen (Seguridad)"
                    else:
                        raw_text = candidates[0].get('content', {}).get('parts', [])[0].get('text', '')
                        clean_text = raw_text.replace('```json', '').replace('```', '').strip()
                        ai_data = json.loads(clean_text)
                        
                        if ai_data.get('es_documento'):
                            numbers_found = str(ai_data.get('numeros', ''))
                            legajo_alumno = re.sub(r'[^0-9]', '', str(attempt.student_legajo))
                            
                            if legajo_alumno and (legajo_alumno in numbers_found or numbers_found in legajo_alumno):
                                ia_success = True
                                break 
                            else:
                                error_actual = f"Legajo no coincide (IA leyó: {numbers_found})"
                        else:
                            error_actual = "No parece un DNI válido"
                except Exception as e:
                    error_actual = f"Error leyendo respuesta IA: {str(e)}"
            
            elif response.status_code == 503:
                error_actual = "Servidor IA ocupado (503)"
                time.sleep(1) 
            elif response.status_code == 404:
                error_actual = "Modelo IA no encontrado (404)"
            else:
                error_actual = f"Error API: {response.status_code}"

        except Exception as e:
            error_actual = f"Error de red/timeout: {str(e)}"

        if not ia_success:
            try:
                AttemptEvent.objects.create(
                    attempt=attempt, 
                    event_type='IDENTITY_MISMATCH', 
                    metadata={'reason': f'Fallo DNI (Intento {intento_num}): {error_actual}'}
                )
            except: pass

    # --- D. DECISIÓN FINAL ---
    if ia_success:
        return JsonResponse({'success': True, 'message': 'Identidad verificada.'})
    else:
        return JsonResponse({
            'success': True, 
            'message': 'Validación guardada para revisión manual.'
        })

# 6. RUNNER (Examen)
# Busca la función 'exam_runner_view' y REEMPLÁZALA por esto:

def exam_runner_view(request, access_code, attempt_id):
    print(f"--- DEBUG: Iniciando examen {access_code} para intento {attempt_id} ---")
    
    try:
        # 1. Intentamos obtener los objetos básicos
        exam = get_object_or_404(Exam, access_code=access_code)
        attempt = get_object_or_404(Attempt, id=attempt_id)
        
        # 2. Verificamos si ya terminó
        if attempt.completed_at:
            return redirect('runner:exam_finished', attempt_id=attempt.id)

        # 3. Cálculo de tiempos
        total_duration = exam.get_total_duration_seconds()
        
        if attempt.start_time:
            elapsed = (timezone.now() - attempt.start_time).total_seconds()
            remaining = max(0, total_duration - elapsed)
            
            saved_answers = attempt.answers or {}
            # Si se acabó el tiempo y no respondió nada, reiniciamos (lógica original)
            if remaining <= 0 and not saved_answers:
                 attempt.start_time = None 
                 attempt.save()
                 remaining = total_duration
        else:
            remaining = total_duration

        # 4. Si se acabó el tiempo real
        if remaining <= 0 and attempt.start_time:
            return redirect('runner:submit_exam', attempt_id=attempt.id)

        # 5. Carga de preguntas (POSIBLE PUNTO DE FALLO)
        print("--- DEBUG: Cargando items del examen ---")
        items = list(exam.items.all())
        
        if not items:
            print("--- WARNING: El examen no tiene preguntas ---")

        if exam.shuffle_items:
            random.Random(str(attempt.id)).shuffle(items)
        
        saved_answers = attempt.answers or {}
        initial_step = len(saved_answers)
        if initial_step >= len(items): initial_step = len(items) - 1

        print("--- DEBUG: Renderizando plantilla ---")
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

    except Exception as e:
        # AQUI ESTÁ LA MAGIA: Imprimimos el error completo en los logs
        print("\n" + "="*50)
        print("¡¡¡ ERROR FATAL EN EXAM RUNNER !!!")
        print(f"Mensaje: {str(e)}")
        print("--- TRACEBACK COMPLETO ---")
        print(traceback.format_exc()) # Esto nos dirá la línea exacta
        print("="*50 + "\n")
        
        # Devolvemos el error en pantalla para que lo veas sin ir a los logs (solo temporalmente)
        return HttpResponse(f"<h2>Error Detectado (Modo Debug)</h2><pre>{traceback.format_exc()}</pre>", status=500)

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

# 8. FINALIZAR
def submit_exam_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    exam = attempt.exam
    score = 0
    questions = exam.items.all()
    answers = attempt.answers or {}

    for q in questions:
        selected = answers.get(str(q.id))
        if selected:
            correct = next((o for o in (q.options or []) if o.get('correct')), None)
            if correct and correct.get('text') == selected:
                link = exam.examitemlink_set.filter(item=q).first()
                score += link.points if link else 1.0

    attempt.score = score
    attempt.completed_at = timezone.now()
    attempt.save()
    return redirect('runner:exam_finished', attempt_id=attempt.id)

# 9. PANTALLA FINAL
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/finished.html', {'attempt': attempt})

# 10. LOGS
@require_POST
def log_event(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        
        if not attempt.start_time:
             return JsonResponse({'status': 'ignored_not_started'}, status=200)

        if attempt.completed_at:
            return JsonResponse({'status': 'ignored_completed'}, status=200)

        data = json.loads(request.body)
        event_type = data.get('event_type')
        metadata = data.get('metadata', {})
        
        valid_types = [t[0] for t in AttemptEvent.EVENT_TYPES]
        if event_type not in valid_types:
            return JsonResponse({'status': 'ignored_invalid'}, status=200)

        if (timezone.now() - attempt.start_time).total_seconds() < 15:
            return JsonResponse({'status': 'ignored_grace'}, status=200)

        AttemptEvent.objects.create(attempt=attempt, event_type=event_type, metadata=metadata)
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
        
        if risk_score > limit_high: 
            status_color = 'red'
        elif risk_score > limit_medium: 
            status_color = 'yellow'
        
        results.append({
            'attempt': attempt, 'risk_score': risk_score,
            'status_color': status_color, 'event_count': events.count()
        })
    return render(request, 'runner/teacher_dashboard.html', {'exam': exam, 'results': results})

@login_required
@user_passes_test(is_staff)
def attempt_detail_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    events = attempt.events.all().order_by('timestamp')
    evidence_list = Evidence.objects.filter(attempt=attempt).order_by('timestamp')
    return render(request, 'runner/attempt_detail.html', {'attempt': attempt, 'events': events, 'evidence_list': evidence_list})

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
