import random
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone  # Necesario para calcular tiempos
from exams.models import Exam
from .models import Attempt

# 1. LOBBY: Solo pide los datos
def lobby_view(request, access_code):
    exam = get_object_or_404(Exam, access_code=access_code)
    
    if request.method == "POST":
        # Crear el intento aquí
        nombre = request.POST.get('full_name')
        legajo = request.POST.get('student_id')
        
        attempt = Attempt.objects.create(
            exam=exam,
            student_name=nombre,
            student_legajo=legajo,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        # REDIRECCIÓN AL TECH CHECK (Paso 2)
        return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=attempt.id)
        
    return render(request, 'runner/lobby.html', {'exam': exam})


# 2. TECH CHECK: Prueba de Cámara y Micrófono
def tech_check_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    return render(request, 'runner/tech_check.html', {
        'exam': exam,
        'attempt': attempt
    })


# 3. RUNNER: El examen en sí
def exam_runner_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    # A. Protección: Si ya terminó, redirigir a pantalla final
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    # B. Cargar preguntas (respetando shuffle)
    items = list(exam.items.all())
    if exam.shuffle_items:
        # Usamos el ID del intento como semilla
        random.Random(str(attempt.id)).shuffle(items)
        
    # C. Cálculo de Tiempos (Server-Side Authority)
    total_duration_seconds = exam.get_total_duration_seconds()
    elapsed_time = (timezone.now() - attempt.start_time).total_seconds()
    remaining_seconds = max(0, total_duration_seconds - elapsed_time)

    # Si se acabó el tiempo global, forzar entrega
    if remaining_seconds <= 0:
        return redirect('runner:submit_exam', attempt_id=attempt.id)
            
    return render(request, 'runner/exam_runner.html', {
        'exam': exam,
        'attempt': attempt,
        'items': items,
        'total_questions': len(items),
        # Pasamos variables de tiempo al template
        'remaining_seconds': int(remaining_seconds),
        'time_per_item': exam.time_per_item,
    })


# 4. GUARDADO AUTOMÁTICO (AJAX)
@require_POST
def save_answer(request, attempt_id):
    """
    Recibe una respuesta individual y la guarda en el JSON del intento.
    """
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        
        # Parseamos los datos del cuerpo (body) de la petición
        data = json.loads(request.body)
        question_id = str(data.get('question_id'))
        selected_option = data.get('answer')
        
        # Actualizamos el diccionario de respuestas
        current_answers = attempt.answers or {}
        current_answers[question_id] = selected_option
        
        attempt.answers = current_answers
        attempt.save(update_fields=['answers', 'last_heartbeat']) 
        
        return JsonResponse({'status': 'ok', 'saved': True})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# 5. FINALIZAR EXAMEN (Lógica de calificación)
def submit_exam_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)

    # Protección: Si ya terminó, no dejar recalcular
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    exam = attempt.exam
    total_score = 0
    
    # Traemos las preguntas y las relaciones (donde está el puntaje)
    # Nota: Para ser precisos con el puntaje, iteramos sobre los links o items
    # Aquí simplificamos asumiendo que el 'score' estaba en la lógica previa o items.
    # Si ExamItemLink tiene 'points', deberíamos usar eso.
    
    questions = exam.items.all()
    student_answers = attempt.answers or {}

    for question in questions:
        # Buscamos la respuesta del alumno
        student_selected = student_answers.get(str(question.id))
        
        if student_selected:
            # Buscamos la opción correcta dentro del JSON de opciones de la pregunta
            # Estructura options: [{'text': 'A', 'correct': True}, ...]
            options = question.options or []
            correct_option = next((opt for opt in options if opt.get('correct') is True), None)
            
            if correct_option and correct_option.get('text') == student_selected:
                # Sumamos punto (aquí asumimos 1 punto por defecto si no usamos ExamItemLink)
                # Para ser perfecto con tu modelo ExamItemLink:
                link = exam.examitemlink_set.filter(item=question).first()
                points = link.points if link else 1.0
                total_score += points

    # Guardamos resultados
    attempt.score = total_score
    attempt.completed_at = timezone.now()
    attempt.save()

    return redirect('runner:exam_finished', attempt_id=attempt.id)


# 6. PANTALLA FINAL
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/finished.html', {'attempt': attempt})
