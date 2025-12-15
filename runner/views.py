import random
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Count
from exams.models import Exam
from .models import Attempt, AttemptEvent

# --- FUNCIONES AUXILIARES ---
def is_staff(user):
    return user.is_staff

# ==========================================
# SECCIÓN ALUMNO (LOBBY & EXAMEN)
# ==========================================

# 1. LOBBY: Lógica de Bloqueo y Reanudación
def lobby_view(request, access_code):
    exam = get_object_or_404(Exam, access_code=access_code)
    
    if request.method == "POST":
        nombre = request.POST.get('full_name', '').strip()
        legajo = request.POST.get('student_id', '').strip()
        
        # A. REGLA DE ORO: ¿Ya lo terminó? -> BLOQUEAR
        finished_attempt = Attempt.objects.filter(
            exam=exam, 
            student_legajo__iexact=legajo,
            completed_at__isnull=False
        ).first()

        if finished_attempt:
            return render(request, 'runner/lobby.html', {
                'exam': exam,
                'error': f'Acceso denegado. El alumno con legajo "{legajo}" ya envió este examen.'
            })
            
        # B. ¿Tiene uno abierto? -> RESUCITAR
        active_attempt = Attempt.objects.filter(
            exam=exam, 
            student_legajo__iexact=legajo,
            completed_at__isnull=True
        ).first()

        if active_attempt:
            active_attempt.student_name = nombre
            active_attempt.save()
            # Redirige al Tech Check primero
            return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=active_attempt.id)

        # C. Es nuevo -> CREAR
        # IMPORTANTE: Al crear, 'start_time' debe quedar vacío (None) hasta que empiece a rendir.
        attempt = Attempt.objects.create(
            exam=exam,
            student_name=nombre,
            student_legajo=legajo,
            ip_address=request.META.get('REMOTE_ADDR')
            # start_time se deja en None por defecto
        )
        return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=attempt.id)
        
    return render(request, 'runner/lobby.html', {'exam': exam})


# 2. TECH CHECK (Hardware)
def tech_check_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/tech_check.html', {'exam': exam, 'attempt': attempt})


# 3. BIOMETRIC GATE (Identidad)
def biometric_gate_view(request, access_code, attempt_id):
    """
    PANTALLA INTERMEDIA: Validación de Identidad y Captura de Ancla.
    """
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    return render(request, 'runner/biometric_gate.html', {
        'exam': exam, 
        'attempt': attempt
    })


# 4. API REGISTRO BIOMÉTRICO
@require_POST
def register_biometrics(request, attempt_id):
    """
    Recibe la foto de referencia del Lobby y la guarda en el Attempt.
    """
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        
        # Guardamos las imágenes en Base64
        if 'reference_face' in data:
            attempt.reference_face_url = data['reference_face']
        
        if 'photo_id' in data:
            attempt.photo_id_url = data['photo_id']
            
        attempt.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# 5. RUNNER (Examen)
def exam_runner_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    # --- CORRECCIÓN CRÍTICA: INICIO DEL RELOJ ---
    # Si start_time es None (es la primera vez que entra a las preguntas),
    # iniciamos el cronómetro AHORA.
    if not attempt.start_time:
        attempt.start_time = timezone.now()
        attempt.save(update_fields=['start_time'])
    # --------------------------------------------

    items = list(exam.items.all())
    if exam.shuffle_items:
        # Usamos el ID del intento como semilla para que el orden sea siempre el mismo para este alumno
        random.Random(str(attempt.id)).shuffle(items)
        
    total_duration = exam.get_total_duration_seconds()
    
    # Calculamos el tiempo transcurrido desde que SE MOSTRARON LAS PREGUNTAS
    elapsed = (timezone.now() - attempt.start_time).total_seconds()
    remaining = max(0, total_duration - elapsed)

    if remaining <= 0:
        return redirect('runner:submit_exam', attempt_id=attempt.id)

    # Lógica de Salto Directo (retomar donde dejó)
    saved_answers = attempt.answers or {}
    initial_step = len(saved_answers)
    
    if initial_step >= len(items):
        initial_step = len(items) - 1

    return render(request, 'runner/exam_runner.html', {
        'exam': exam,
        'attempt': attempt,
        'items': items,
        'total_questions': len(items),
        'remaining_seconds': int(remaining),
        'time_per_item': exam.time_per_item,
        'initial_step': initial_step,
    })


# 6. GUARDAR RESPUESTA
@require_POST
def save_answer(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        
        current_answers = attempt.answers or {}
        current_answers[str(data.get('question_id'))] = data.get('answer')
        
        attempt.answers = current_answers
        # Actualizamos heartbeat para saber que sigue vivo
        attempt.save(update_fields=['answers', 'last_heartbeat']) 
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error'}, status=400)


# 7. FINALIZAR
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
            # Buscamos la opción correcta
            correct = next((o for o in (q.options or []) if o.get('correct')), None)
            if correct and correct.get('text') == selected:
                # Buscamos el puntaje específico de esa pregunta en este examen
                link = exam.examitemlink_set.filter(item=q).first()
                score += link.points if link else 1.0

    attempt.score = score
    attempt.completed_at = timezone.now()
    attempt.save()

    return redirect('runner:exam_finished', attempt_id=attempt.id)


# 8. PANTALLA FINAL
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/finished.html', {'attempt': attempt})


# 9. LOG DE SEGURIDAD
@require_POST
def log_event(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        
        event_type = data.get('event_type')
        metadata = data.get('metadata', {})
        
        # Validar que el tipo de evento exista en nuestro modelo
        valid_types = [t[0] for t in AttemptEvent.EVENT_TYPES]
        if event_type not in valid_types:
            return JsonResponse({'status': 'ignored'}, status=200)

        AttemptEvent.objects.create(
            attempt=attempt,
            event_type=event_type,
            metadata=metadata
        )
        
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ==========================================
# SECCIÓN DOCENTE (DASHBOARD & AUDITORÍA)
# ==========================================

# 10. DASHBOARD DEL DOCENTE (Listado de Alumnos con Semáforo)
@login_required
@user_passes_test(is_staff)
def teacher_dashboard_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    # Traemos los intentos y pre-cargamos los eventos para optimizar DB
    attempts = Attempt.objects.filter(exam=exam).order_by('-start_time').prefetch_related('events')

    results = []
    
    for attempt in attempts:
        events = attempt.events.all()
        
        # --- CÁLCULO DE RIESGO (ANTIFRAUDE IQ) ---
        risk_score = 0
        
        # Pesos basados en la severidad del evento
        # FOCUS_LOST: Distracción menor/alt-tab
        # FULLSCREEN_EXIT: Intento de manipular el entorno
        # NO_FACE: Abandono del puesto
        # MULTI_FACE: Ayuda externa (Grave)
        # IDENTITY_MISMATCH: Suplantación (Crítico)
        
        risk_score += events.filter(event_type='FOCUS_LOST').count() * 1
        risk_score += events.filter(event_type='FULLSCREEN_EXIT').count() * 2
        risk_score += events.filter(event_type='NO_FACE').count() * 3
        risk_score += events.filter(event_type='MULTI_FACE').count() * 5
        risk_score += events.filter(event_type='IDENTITY_MISMATCH').count() * 10
        
        # Semáforo de Integridad
        status_color = 'green'
        status_text = 'Confiable'
        show_grade = True # Por defecto mostramos la nota
        
        if risk_score > 10:
            status_color = 'red'
            status_text = 'Crítico'
            show_grade = False # Riesgo alto: Ocultar nota
        elif risk_score > 4:
            status_color = 'yellow'
            status_text = 'Revisar'
            show_grade = False # Riesgo medio: Ocultar nota
            
        results.append({
            'attempt': attempt,
            'risk_score': risk_score,
            'status_color': status_color,
            'status_text': status_text,
            'show_grade': show_grade,
            'event_count': events.count()
        })

    return render(request, 'runner/teacher_dashboard.html', {
        'exam': exam,
        'results': results
    })


# 11. DETALLE DEL INTENTO (Auditoría Forense)
@login_required
@user_passes_test(is_staff)
def attempt_detail_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    events = attempt.events.all().order_by('timestamp')
    
    return render(request, 'runner/attempt_detail.html', {
        'attempt': attempt,
        'events': events
    })


# 12. HOME DOCENTE (Lista de Exámenes)
@login_required
@user_passes_test(is_staff)
def teacher_home_view(request):
    """
    Pantalla principal ("Mis Exámenes"): Muestra la lista para elegir cuál corregir.
    """
    # Trae todos los exámenes ordenados por el más nuevo
    exams = Exam.objects.all().order_by('-id') 
    
    return render(request, 'runner/teacher_home.html', {
        'exams': exams
    })

# 13. PORTAL PRINCIPAL (LANDING PAGE)
@login_required
@user_passes_test(is_staff)
def portal_docente_view(request):
    """
    Centro de Comando del Docente.
    Desde aquí deriva a: Exámenes Online, Generador Papel o Admin.
    """
    return render(request, 'runner/portal_docente.html')
