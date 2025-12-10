from django.urls import path
from . import views

app_name = 'classroom_exams'

urlpatterns = [
    path('', views.acceso_alumno, name='acceso'),
]
