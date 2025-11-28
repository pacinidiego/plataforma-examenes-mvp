import uuid
from django.db import models
from django.conf import settings
from exams.models import Exam

class Attempt(models.Model):
    """
    Representa el intento de un alumno de resolver un examen.
    Guarda el estado, las respuestas y el tiempo.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relaciones
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    
    # Tiempos
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="Inicio")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Fin / Entrega")
    
    # Resiliencia y Seguridad
    # 'last_heartbeat' se actualiza cada 30s. Si es muy viejo, asumimos desconexión.
    last_heartbeat = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Respuestas
    # Guardamos un JSON simple: { "item_id": "opcion_elegida", ... }
    # Esto permite autosave rápido sin crear miles de filas en la BD.
    answers = models.JSONField(default=dict, blank=True)
    
    # Resultado
    score = models.FloatField(null=True, blank=True, verbose_name="Puntaje Final")
    
    # Estado
    is_active = models.BooleanField(default=True, help_text="True si el examen está en curso")

    class Meta:
        ordering = ['-start_time']
        verbose_name = "Intento de Examen"
        verbose_name_plural = "Intentos"

    def __str__(self):
        return f"{self.user.username} - {self.exam.title}"
