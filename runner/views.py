import random
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from exams.models import Exam
from .models import Attempt

# 1. LOBBY: Lógica de Bloqueo / Reanudación
def lobby_view(request, access_code):
    exam = get_object_or_404(Exam, access_code=access_code)
    
    if request.method == "POST":
        # Usamos .strip() para quitar espacios accidentales al inicio/final
        nombre = request.POST.get('full_name', '').strip()
        legajo = request.POST.get('student_id', '').strip()
        
        # BUSCAR SI YA EXISTE UN INTENTO
        existing_attempt = Attempt.objects.filter(
            exam=exam, 
            student_legajo__iexact=legajo  # iexact ignora mayúsculas/minúsculas
        ).first()

        if existing_attempt:
            # CASO A: YA TERMINÓ -> BLOQUEAR
            if existing_attempt.completed_at:
                return render(request, 'runner/lobby.html', {
                    'exam': exam,
                    'error': f'Acceso denegado. El legajo "{legajo}" ya completó este examen.'
                })
            
            # CASO B: ESTÁ EN CURSO -> REANUDAR (No crea uno nuevo)
            # Actualizamos el nombre por si lo escribió mejor esta vez
            existing_attempt.student_name = nombre
            existing_attempt.save()
            return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=existing_attempt.id)

        # CASO C: ES NUEVO -> CREAR
        attempt = Attempt.objects.create(
            exam=exam,
            student_name=nombre,
            student_legajo=legajo,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=attempt.id)
        
    return render(request, 'runner/lobby.html', {'exam': exam})


# 2. TECH CHECK
def tech_check_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/tech_check.html', {'exam': exam, 'attempt': attempt})


# 3. RUNNER (Examen)
def exam_runner_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    # Si ya terminó, lo echamos fuera a la pantalla final
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    items = list(exam.items.all())
    if exam.shuffle_items:
        random.Random(str(attempt.id)).shuffle(items)
        
    # Tiempo restante
    total_duration = exam.get_total_duration_seconds()
    elapsed = (timezone.now() - attempt.start_time).total_seconds()
    remaining = max(0, total_duration - elapsed)

    if remaining <= 0:
        return redirect('runner:submit_exam', attempt_id=attempt.id)
            
    return render(request, 'runner/exam_runner.html', {
        'exam': exam,
        'attempt': attempt,
        'items': items,
        'total_questions': len(items),
        'remaining_seconds': int(remaining),
        'time_per_item': exam.time_per_item,
    })


# 4. SAVE ANSWER
@require_POST
def save_answer(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        
        current_answers = attempt.answers or {}
        current_answers[str(data.get('question_id'))] = data.get('answer')
        
        attempt.answers = current_answers
        attempt.save(update_fields=['answers', 'last_heartbeat']) 
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error'}, status=400)


# 5. SUBMIT EXAM
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
    attempt.completed_at = timezone.now() # MARCA DE TIEMPO FINAL
    attempt.save()

    return redirect('runner:exam_finished', attempt_id=attempt.id)


# 6. FINISHED SCREEN
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/finished.html', {'attempt': attempt})
