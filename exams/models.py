import uuid
from django.db import models
from django.conf import settings
from tenancy.models import Tenant

# Create your models here.

class Item(models.Model):
    """
    Una Pregunta (Item) en el Banco de Preguntas.
    """
    class ItemType(models.TextChoices):
        MULTIPLE_CHOICE = 'MC', 'Opción Múltiple (MC)'
        SHORT_ANSWER = 'SA', 'Respuesta Corta (SA)'
        ESSAY = 'ES', 'Ensayo (ES)'

    class Difficulty(models.IntegerChoices):
        EASY = 1, 'Fácil'
        MEDIUM = 2, 'Media'
        HARD = 3, 'Difícil'

    # Relaciones
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="items")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Contenido
    item_type = models.CharField(max_length=2, choices=ItemType.choices, default=ItemType.MULTIPLE_CHOICE)
    stem = models.TextField(verbose_name="Enunciado (Stem)")
    options = models.JSONField(null=True, blank=True, help_text="Opciones para MC (ej. [{'text': 'A', 'correct': True}, ...])")
    
    # Metadatos
    difficulty = models.IntegerField(choices=Difficulty.choices, default=Difficulty.MEDIUM)
    tags = models.CharField(max_length=255, blank=True, help_text="Etiquetas separadas por comas")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pregunta (Item)"
        verbose_name_plural = "Banco de Preguntas"
        unique_together = ('tenant', 'stem')

    def __str__(self):
        return self.stem[:60]


class Exam(models.Model):
    """
    Un Examen, que es una colección ordenada de Items.
    """
    
    # --- [CORRECCIÓN S1e] ---
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('published', 'Publicado'),
        ('archived', 'Archivado'),
    ]

    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='draft', # Usamos el string simple 'draft'
        db_index=True
    )
    # --- [FIN CORRECCIÓN] ---
