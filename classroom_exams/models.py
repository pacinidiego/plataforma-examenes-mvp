from django.db import models
from tenancy.models import Tenant
from exams.models import Item  # Importamos tus preguntas existentes

class KioskConfig(models.Model):
    # Configuración general del examen de aula
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=200, help_text="Ej: Final Matemática")
    pin_profesor = models.CharField(max_length=4, help_text="PIN para cerrar sesión")
    
    # --- NUEVO CAMPO AGREGADO ---
    duracion_minutos = models.PositiveIntegerField(default=60, help_text="Tiempo límite en minutos")
    # ----------------------------

    # Reglas de mezcla
    cantidad_faciles = models.PositiveIntegerField(default=5)
    cantidad_medias = models.PositiveIntegerField(default=3)
    cantidad_dificiles = models.PositiveIntegerField(default=2)
    
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class KioskSession(models.Model):
    # El intento del alumno
    config = models.ForeignKey(KioskConfig, on_delete=models.CASCADE)
    alumno_nombre = models.CharField(max_length=200)
    alumno_dni = models.CharField(max_length=50)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    nota_final = models.FloatField(null=True, blank=True)
    indice_pregunta_actual = models.PositiveIntegerField(default=1)
    
    # Aquí guardamos la estructura exacta que vio el alumno
    examen_snapshot = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.alumno_nombre} - {self.alumno_dni}"
