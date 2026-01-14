import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from exams.models import Exam

class Attempt(models.Model):
    """
    Representa el intento de un alumno.
    Soporta alumnos logueados (user) o invitados por link (student_name).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relaciones
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='attempts')
    
    # Datos del Alumno
    student_name = models.CharField(max_length=255, blank=True, verbose_name="Nombre del Alumno")
    student_legajo = models.CharField(max_length=100, blank=True, verbose_name="Legajo/DNI")
    
    # BIOMETRÍA Y SEGURIDAD
    # Guardamos la RUTA (path) del archivo, no la URL firmada que caduca
    photo_id_url = models.TextField(null=True, blank=True, verbose_name="Foto DNI (Path)")
    reference_face_url = models.TextField(null=True, blank=True, verbose_name="Foto Cara Ref (Path)")
    
    # Tiempos
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="Inicio") 
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completado el")
    
    last_heartbeat = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Respuestas y Calificación
    answers = models.JSONField(default=dict, blank=True)
    score = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # --- CAMPOS DE REVISIÓN DOCENTE ---
    REVIEW_STATUS_CHOICES = [
        ('pending', 'Pendiente de Revisión'),
        ('approved', 'Aprobado / Validado'),
        ('rejected', 'Anulado (Fraude Detectado)'),
        ('revision', 'Requiere Ajuste Manual'),
    ]
    
    review_status = models.CharField(
        max_length=20, 
        choices=REVIEW_STATUS_CHOICES, 
        default='pending',
        verbose_name="Estado de Revisión"
    )
    teacher_comment = models.TextField(
        blank=True, 
        null=True, 
        help_text="Feedback del docente al alumno o justificación de anulación"
    )
    
    # NUEVO: Lista de IDs de preguntas anuladas por fraude (ej: ["102", "105"])
    penalized_items = models.JSONField(default=list, blank=True)
    
    # NUEVO: Puntos a restar manualmente de la nota final
    penalty_points = models.FloatField(default=0.0, verbose_name="Puntos de Penalidad")

    # --- PROPIEDADES DINÁMICAS (Arreglo definitivo XML Error) ---
    @property
    def signed_photo_id_url(self):
        """Genera un link válido por 1h al momento de consultar"""
        if self.photo_id_url:
            # Soporte retroactivo: si ya es URL, la devuelve. Si es path, la firma.
            if self.photo_id_url.startswith('http'): return self.photo_id_url
            try: return default_storage.url(self.photo_id_url)
            except: return ""
        return None

    @property
    def signed_face_url(self):
        if self.reference_face_url:
            if self.reference_face_url.startswith('http'): return self.reference_face_url
            try: return default_storage.url(self.reference_face_url)
            except: return ""
        return None

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        nombre = self.user.username if self.user else f"{self.student_name} ({self.student_legajo})"
        return f"{nombre} - {self.exam.title}"


class AttemptEvent(models.Model):
    """
    Bitácora de seguridad (Caja Negra).
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='events')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    EVENT_TYPES = [
        ('SESSION_RESUME', 'Reconexión / Reanudación'),
        ('FOCUS_LOST', 'Pérdida de Foco (Cambio de Pestaña)'),
        ('FULLSCREEN_EXIT', 'Salida de Pantalla Completa'),
        ('MULTI_FACE', 'Múltiples rostros detectados'),
        ('NO_FACE', 'Rostro no detectado'),
        ('AUDIO_SPIKE', 'Sonido/Voz detectada'),
        ('IDENTITY_MISMATCH', 'Suplantación de Identidad'),
        ('CAMERA_ERROR', 'Error de Cámara'),
        ('ANSWER_SAVED', 'Respuesta Guardada'),
    ]
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    metadata = models.JSONField(default=dict, blank=True)
    evidence_url = models.TextField(null=True, blank=True) # Guardamos PATH

    @property
    def signed_evidence_url(self):
        path = self.evidence_url or self.metadata.get('evidence_url')
        if path:
            if path.startswith('http'): return path
            try: return default_storage.url(path)
            except: return ""
        return None

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.timestamp.strftime('%H:%M:%S')}"


class Evidence(models.Model):
    """
    Almacena fotos individuales de validación o monitoreo.
    """
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='evidence_list')
    file_url = models.TextField(help_text="Ruta del archivo") # Guardamos PATH
    timestamp = models.DateTimeField(default=timezone.now)
    gemini_analysis = models.JSONField(default=dict, blank=True, help_text="Respuesta cruda de la IA")

    @property
    def signed_file_url(self):
        if self.file_url:
            if self.file_url.startswith('http'): return self.file_url
            try: return default_storage.url(self.file_url)
            except: return ""
        return None

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Evidencia {self.id} - {self.attempt}"
