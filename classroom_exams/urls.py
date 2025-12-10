from django.urls import path
from . import views

app_name = 'classroom_exams'

urlpatterns = [
    path('', views.acceso_alumno, name='acceso'),
    path('reglas/', views.instrucciones_examen, name='instrucciones'), # <--- NUEVA
    path('rendir/', views.rendir_examen, name='rendir_examen'), # Quitamos el número de la URL para que no hagan trampa escribiendo /rendir/5
    path('resultado/', views.resultado_examen, name='resultado_examen'),
    path('accion-profesor/', views.accion_profesor, name='accion_profesor'),
]
