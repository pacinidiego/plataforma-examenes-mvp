from django.contrib import admin
from django.http import HttpResponse
import csv
from .models import KioskConfig, KioskSession

# --- 1. Definimos la función de exportación ---
def exportar_notas_csv(modeladmin, request, queryset):
    """
    Esta función toma los elementos seleccionados en el admin 
    y genera un archivo CSV para descargar.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reporte_notas.csv"'
    
    writer = csv.writer(response)
    # Escribimos la cabecera del Excel
    writer.writerow(['Nombre del Alumno', 'DNI', 'Nota Final', 'Fecha Inicio', 'Examen'])
    
    # Escribimos los datos de cada fila seleccionada
    for sesion in queryset:
        writer.writerow([
            sesion.alumno_nombre,
            sesion.alumno_dni,
            sesion.nota_final,
            sesion.fecha_inicio.strftime("%Y-%m-%d %H:%M") if sesion.fecha_inicio else '-',
            sesion.config.nombre
        ])
        
    return response

# Texto que aparecerá en el menú desplegable
exportar_notas_csv.short_description = "Descargar notas seleccionadas (CSV)"


# --- 2. Configuramos los modelos en el Admin ---

@admin.register(KioskConfig)
class KioskConfigAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tenant', 'duracion_minutos', 'activo')
    list_filter = ('tenant', 'activo')

@admin.register(KioskSession)
class KioskSessionAdmin(admin.ModelAdmin):
    # Columnas que verás en la lista
    list_display = ('alumno_nombre', 'alumno_dni', 'nota_final', 'fecha_inicio', 'examen_nombre')
    
    # Filtros laterales (muy útil para buscar por examen)
    list_filter = ('config', 'fecha_inicio')
    
    # Buscador (para encontrar rápido un DNI)
    search_fields = ('alumno_nombre', 'alumno_dni')
    
    # AQUÍ AGREGAMOS LA ACCIÓN DE DESCARGA
    actions = [exportar_notas_csv]

    # Un pequeño truco para mostrar el nombre del examen en la tabla
    def examen_nombre(self, obj):
        return obj.config.nombre
    examen_nombre.short_description = 'Examen'
