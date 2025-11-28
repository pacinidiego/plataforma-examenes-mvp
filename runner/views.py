from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from exams.models import Exam

def lobby_view(request, access_code):
    # Si esto falla, devuelve 404. 
    # Pero al menos sabremos que llegó a la vista.
    exam = get_object_or_404(Exam, access_code=access_code)
    return HttpResponse(f"<h1>Lobby del Examen: {exam.title}</h1>")

def exam_runner_view(request, access_code):
    return HttpResponse("<h1>Runner</h1>")
