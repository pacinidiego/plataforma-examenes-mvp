from django.contrib import admin
from .models import KioskConfig, KioskSession

@admin.register(KioskConfig)
class KioskConfigAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tenant', 'activo', 'pin_profesor')
    list_filter = ('tenant', 'activo')

@admin.register(KioskSession)
class KioskSessionAdmin(admin.ModelAdmin):
    list_display = ('alumno_nombre', 'alumno_dni', 'config', 'fecha_inicio', 'nota_final')
    list_filter = ('config', 'fecha_inicio')
    readonly_fields = ('examen_snapshot',) # Para ver el JSON pero no editarlo por error
