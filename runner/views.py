import random
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
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
    
    # Cargar preguntas (respetando shuffle)
    items = list(exam.items.all())
    if exam.shuffle_items:
        # Usamos el ID del intento como semilla para que el orden sea aleatorio 
        # pero CONSISTENTE si recarga la página (misma semilla = mismo desorden)
        random.Random(str(attempt.id)).shuffle(items)
            
    return render(request, 'runner/exam_runner.html', {
        'exam': exam,
        'attempt': attempt,
        'items': items,
        'total_questions': len(items)
    })
