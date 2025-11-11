from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from tenancy.models import Tenant

# (Spec S1: Banco de ítems (MC, corta, caso))
class Item(models.Model):
    """
    Una única pregunta (Item) en un banco de preguntas.
    Pertenece a un Tenant y es creada por un Docente.
    """
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
    
    # (Spec S1: metadatos (dificultad, tags))
    tags = models.CharField(max_length=255, blank=True, verbose_name=_("Etiquetas (separadas por coma)"))
    difficulty = models.PositiveSmallIntegerField(default=1, help_text=_("Nivel de dificultad (1-5)"), verbose_name=_("Dificultad"))

    # Contenido de la pregunta
    stem = models.TextField(verbose_name=_("Enunciado (Stem)"))
    
    # Opciones (solo para MC)
    options = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name=_("Opciones (para MC)"),
        help_text=_("Formato JSON: [{'text': 'Opción A', 'correct': True}, ...]")
    )

    # (Spec IT-05: Ítem de caso largo)
    case_content = models.TextField(
        blank=True, 
        null=True, 
        verbose_name=_("Contenido del Caso (si aplica)"),
        help_text=_("El texto/contexto principal para un ítem de 'Estudio de Caso'.")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Ítem de Pregunta")
        verbose_name_plural = _("Banco de Ítems")

    def __str__(self):
        return f"[{self.get_item_type_display()}] {self.stem[:50]}... ({self.tenant.name})"


class Exam(models.Model):
    """
    Un Examen, que es una colección ordenada de Items.
    (Spec S1: Constructor)
    """
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
    
    # (Spec S1: Constructor)
    items = models.ManyToManyField(
        Item, 
        through='ExamItemLink', # Ahora 'ExamItemLink' está definida abajo
        related_name='exams',
        verbose_name=_("Ítems Incluidos")
    )
    
    # (Spec S1: seed/shuffle)
    # (Spec G: Randomización)
    shuffle_items = models.BooleanField(default=True, verbose_name=_("Mezclar orden de preguntas (RA-02)"))
    shuffle_options = models.BooleanField(default=True, verbose_name=_("Mezclar opciones de MC (RA-03)"))
    
    created_at = models.DateTimeField(auto_now_add
