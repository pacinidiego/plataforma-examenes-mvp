import uuid
from django.db import models
from django.conf import settings
from exams.models import Exam

class Attempt(models.Model):
    """
    Representa el intento de un alumno.
    Soporta alumnos logueados (user) o invitados por link (student_name).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relaciones
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    
    # Usuario (Opcional: para cuando integremos login real)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='attempts')
    
    # Datos del Alumno (Para acceso actual vía Link)
    student_name = models.CharField(max_length=255, blank=True, verbose_name="Nombre del Alumno")
    student_legajo = models.CharField(max_length=100, blank=True, verbose_name="Legajo/DNI")
    
    # Tiempos
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="Inicio")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Fin") # Mantenemos este por compatibilidad histórica
    
    # === NUEVO CAMPO REQUERIDO ===
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completado el")
    # =============================

    last_heartbeat = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Respuestas (JSON)
    answers = models.JSONField(default=dict, blank=True)
    score = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        if self.user:
            return f"{self.user.username} - {self.exam.title}"
        return f"{self.student_name} ({self.student_legajo}) - {self.exam.title}"
