from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from tenancy.models import Tenant

# (Spec S1: Banco de Preguntas (MC, corta, caso))
class Item(models.Model):
    class ItemType(models.TextChoices):
        MULTIPLE_CHOICE = 'MC', _('Opción Múltiple (MC)')
        SHORT_ANSWER = 'SHORT', _('Respuesta Corta')
        CASE_STUDY = 'CASE', _('Estudio de Caso')

    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name='items',
        verbose_name=_("Institución")
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='items_authored',
        verbose_name=_("Autor (Docente)")
    )
    
    item_type = models.CharField(
        max_length=10, 
        choices=ItemType.choices, 
        default=ItemType.MULTIPLE_CHOICE,
        verbose_name=_("Tipo de Ítem")
    )
    
    tags = models.CharField(
        max_length=255, 
        blank=True, 
        verbose_name=_("Etiquetas"),
        help_text=_("Escribe las etiquetas separadas por coma (ej: algebra, ecuaciones, primer_año)")
    )

    difficulty = models.PositiveSmallIntegerField(default=1, help_text=_("Nivel de dificultad (1-5)"), verbose_name=_("Dificultad"))

    # (Fix Bug "Casi Igual"): Limpiamos el 'stem' en el 'save()'
    stem = models.TextField(verbose_name=_("Enunciado (Stem)"))
    
    options = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name=_("Opciones (para MC)"),
        help_text=_("Formato JSON: [{'text': 'Opción A', 'correct': True}, ...]")
    )

    case_content = models.TextField(
        blank=True, 
        null=True, 
        verbose_name=_("Contenido del Caso (si aplica)"),
        help_text=_("El texto/contexto principal para un ítem de 'Estudio de Caso'.")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Pregunta")
        # --- !! CORRECCIÓN DE TERMINOLOGÍA (Req #4) !! ---
        verbose_name_plural = _("Banco de Preguntas")
        
        # --- !! CORRECCIÓN (BUG #2) !! ---
        # No puede existir el mismo enunciado dos veces EN EL MISMO TENANT
        unique_together = ('tenant', 'stem')

    def __str__(self):
        return f"[{self.get_item_type_display()}] {self.stem[:50]}... ({self.tenant.name})"
    
    def save(self, *args, **kwargs):
        # (Fix Bug "Casi Igual"): Limpiamos el 'stem' antes de guardarlo.
        # Esto no soluciona el "(super usuario)" pero sí " hola " vs "hola"
        if self.stem:
            self.stem = " ".join(self.stem.split())
        super().save(*args, **kwargs)


class Exam(models.Model):
    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name='exams',
        verbose_name=_("Institución")
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='exams_authored',
        verbose_name=_("Autor (Docente)")
    )
    title = models.CharField(max_length=255, verbose_name=_("Título del Examen"))
    
    items = models.ManyToManyField(
        Item, 
        through='ExamItemLink',
        related_name='exams',
        verbose_name=_("Ítems Incluidos")
    )
    
    shuffle_items = models.BooleanField(default=True, verbose_name=_("Mezclar orden de preguntas (RA-02)"))
    shuffle_options = models.BooleanField(default=True, verbose_name=_("Mezclar opciones de MC (RA-03)"))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Examen")
        verbose_name_plural = _("Exámenes")

    def __str__(self):
        return f"{self.title} ({self.tenant.name})"


class ExamItemLink(models.Model):
    exam = models.ForeignKey(
        'exams.Exam', 
        on_delete=models.CASCADE
    )
    item = models.ForeignKey(
        Item, 
        on_delete=models.CASCADE
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name=_("Orden"))
    points = models.PositiveSmallIntegerField(default=1, verbose_name=_("Puntaje"))

    class Meta:
        ordering = ['order']
        unique_together = ('exam', 'item')
