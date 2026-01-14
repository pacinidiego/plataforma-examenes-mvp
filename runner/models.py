import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage # <--- IMPORTANTE
from exams.models import Exam

class Attempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='attempts')
    
    student_name = models.CharField(max_length=255, blank=True)
    student_legajo = models.CharField(max_length=100, blank=True)
    
    # AHORA GUARDAMOS LA RUTA (PATH), NO LA URL COMPLETA
    photo_id_url = models.TextField(null=True, blank=True)
    reference_face_url = models.TextField(null=True, blank=True)
    
    start_time = models.DateTimeField(auto_now_add=True) 
    end_time = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    answers = models.JSONField(default=dict, blank=True)
    score = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pendiente de Revisión'),
        ('approved', 'Aprobado / Validado'),
        ('rejected', 'Anulado (Fraude Detectado)'),
        ('revision', 'Requiere Ajuste Manual'),
    ]
    
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default='pending')
    teacher_comment = models.TextField(blank=True, null=True)
    
    penalized_items = models.JSONField(default=list, blank=True)
    penalty_points = models.FloatField(default=0.0)

    # --- GENERADORES DE LINKS DINÁMICOS (SOLUCIÓN DEFINITIVA) ---
    @property
    def signed_photo_id_url(self):
        """Genera un link fresco válido por 1h cada vez que se pide"""
        if self.photo_id_url:
            # Si es viejo (http...) lo devolvemos, si es ruta, firmamos
            if self.photo_id_url.startswith('http'): return self.photo_id_url
            return default_storage.url(self.photo_id_url)
        return None

    @property
    def signed_face_url(self):
        if self.reference_face_url:
            if self.reference_face_url.startswith('http'): return self.reference_face_url
            return default_storage.url(self.reference_face_url)
        return None

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.student_name} - {self.exam.title}"


class AttemptEvent(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='events')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    EVENT_TYPES = [
        ('SESSION_RESUME', 'Reconexión'), ('FOCUS_LOST', 'Pérdida de Foco'),
        ('FULLSCREEN_EXIT', 'Salida Pantalla'), ('MULTI_FACE', 'Múltiples rostros'),
        ('NO_FACE', 'Sin rostro'), ('IDENTITY_MISMATCH', 'Identidad errónea'),
        ('CAMERA_ERROR', 'Error Cámara'), ('ANSWER_SAVED', 'Respuesta Guardada'),
    ]
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    metadata = models.JSONField(default=dict, blank=True)
    evidence_url = models.URLField(null=True, blank=True) # Guarda ruta o URL

    @property
    def signed_evidence_url(self):
        # Primero buscamos en el campo directo
        path = self.evidence_url
        # Si no, buscamos en metadata (backup)
        if not path and self.metadata:
            path = self.metadata.get('evidence_url')
        
        if path:
            if path.startswith('http'): return path
            return default_storage.url(path)
        return None

    class Meta: ordering = ['timestamp']


class Evidence(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='evidence_list')
    file_url = models.TextField() # Guarda la RUTA del archivo
    timestamp = models.DateTimeField(default=timezone.now)
    gemini_analysis = models.JSONField(default=dict, blank=True)

    @property
    def signed_file_url(self):
        if self.file_url:
            if self.file_url.startswith('http'): return self.file_url
            return default_storage.url(self.file_url)
        return None

    class Meta: ordering = ['timestamp']
