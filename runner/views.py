from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from exams.models import Exam

# Vista del Lobby (Entrada)
def lobby_view(request, access_code):
    # Buscamos el examen por su código de acceso
    exam = get_object_or_404(Exam, access_code=access_code)
    
    # Renderizamos la plantilla linda
    return render(request, 'runner/lobby.html', {
        'exam': exam
    })

# Vista del Runner (Examen)
def exam_runner_view(request, access_code):
    if request.method == "POST":
        # Aquí procesaremos el inicio del intento (crear Attempt)
        # Por ahora, solo mostramos que llegaron los datos
        nombre = request.POST.get('full_name')
        legajo = request.POST.get('student_id')
        return HttpResponse(f"<h1>Iniciando examen para: {nombre} ({legajo})</h1>")
    
    # Si intentan entrar por GET sin pasar por el lobby, los mandamos al lobby
    # (Esto es seguridad básica para que no se salten el login)
    return redirect('runner:lobby', access_code=access_code)
