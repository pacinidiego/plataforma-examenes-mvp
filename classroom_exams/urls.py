from django.urls import path
from . import views

app_name = 'classroom_exams'

urlpatterns = [
    path('', views.acceso_alumno, name='acceso'),
    path('rendir/', views.rendir_examen, name='rendir_examen'),
    path('resultado/', views.resultado_examen, name='resultado_examen'),
    path('accion-profesor/', views.accion_profesor, name='accion_profesor'),
]
