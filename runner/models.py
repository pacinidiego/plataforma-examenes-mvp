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
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completado el")
    
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


class AttemptEvent(models.Model):
    """
    Bitácora de seguridad (Caja Negra).
    Registra cada incidente sospechoso o técnico durante el examen.
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='events')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Tipos de eventos definidos en la especificación
    EVENT_TYPES = [
        ('SESSION_RESUME', 'Reconexión / Reanudación'),
        ('FOCUS_LOST', 'Pérdida de Foco (Cambio de Pestaña)'),
        ('FULLSCREEN_EXIT', 'Salida de Pantalla Completa'),
        ('MULTI_FACE', 'Múltiples rostros detectados'),
        ('NO_FACE', 'Rostro no detectado'),
        ('AUDIO_SPIKE', 'Sonido/Voz detectada'),
    ]
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    
    # Datos técnicos (Duración del desvío, confianza de la IA, navegador, etc.)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Para el futuro: Link a la foto de evidencia en S3/R2
    evidence_url = models.URLField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.timestamp.strftime('%H:%M:%S')}"
