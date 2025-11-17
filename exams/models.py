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
    
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('published', 'Publicado'),
        ('archived', 'Archivado'),
    ]

    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='draft',
        db_index=True
    )

    access_code = models.UUIDField(
        default=uuid.uuid4, 
        editable=False, 
        unique=True,
        help_text="UUID único para el enlace de acceso del alumno"
    )
    published_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Fecha en que el examen fue publicado"
    )

    # Relaciones
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="exams")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Contenido
    title = models.CharField(max_length=255)
    
    # Campos que faltaban (del error 500)
    shuffle_items = models.BooleanField(
        default=True, 
        verbose_name="Mezclar preguntas"
    ) # Toggle RA-02 
    
    shuffle_options = models.BooleanField(
        default=True, 
        verbose_name="Mezclar opciones"
    ) # Toggle RA-03 
    
    items = models.ManyToManyField(
        Item,
        through='ExamItemLink',
        related_name='exams'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Examen"
        verbose_name_plural = "Exámenes"
        ordering = ['-created_at']

    def __str__(self):
        return self.title


# =========================================================
# ESTA CLASE FALTABA EN GITHUB (causando el Build Error)
# =========================================================
class ExamItemLink(models.Model):
    """
    Tabla intermedia (Through model) que conecta Exam e Item.
    """
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        unique_together = ('exam', 'item')

    def save(self, *args, **kwargs):
        if self.order == 0:
            last_item = ExamItemLink.objects.filter(exam=self.exam).order_by('-order').first()
            self.order = (last_item.order + 1) if last_item else 1
        super().save(*args, **kwargs)
