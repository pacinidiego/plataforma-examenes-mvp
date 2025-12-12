from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import reverse
import csv
from .models import KioskConfig, KioskSession

# --- 1. Definimos la función de exportación (CSV) ---
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

# Texto que aparecerá en el menú desplegable "Action"
exportar_notas_csv.short_description = "Descargar notas seleccionadas (CSV)"


# --- 2. Configuramos los modelos en el Admin ---

@admin.register(KioskConfig)
class KioskConfigAdmin(admin.ModelAdmin):
    # Agregamos 'btn_pdf' al final de la lista
    list_display = ('nombre', 'tenant', 'duracion_minutos', 'activo', 'btn_pdf')
    list_filter = ('tenant', 'activo')
    search_fields = ('nombre',)

    # --- FUNCIÓN QUE CREA EL BOTÓN PDF ---
    def btn_pdf(self, obj):
        # Generamos la URL dinámicamente apuntando a la vista del PDF
        try:
            url = reverse('classroom_exams:pdf_variantes', args=[obj.id])
            
            return format_html(
                '<a class="button" href="{}" style="background-color:#79aec8; color:white; padding: 4px 10px; border-radius: 4px; font-weight: bold;">🖨️ PDF 3 Temas</a>',
                url
            )
        except Exception:
            return "-"

    btn_pdf.short_description = "Descargar Examen"


@admin.register(KioskSession)
class KioskSessionAdmin(admin.ModelAdmin):
    # Agregamos 'ver_examen_btn' a la lista de columnas que se muestran
    list_display = ('alumno_nombre', 'alumno_dni', 'nota_final', 'fecha_inicio', 'examen_nombre', 'ver_examen_btn')
    
    list_filter = ('config', 'fecha_inicio')
    search_fields = ('alumno_nombre', 'alumno_dni')
    actions = [exportar_notas_csv]

    def examen_nombre(self, obj):
        return obj.config.nombre
    examen_nombre.short_description = 'Examen'

    # --- FUNCIÓN QUE CREA EL BOTÓN VER REVISIÓN ---
    def ver_examen_btn(self, obj):
        # Solo mostramos el botón si el examen tiene preguntas guardadas (snapshot)
        if obj.examen_snapshot:
            # Generamos la URL dinámicamente
            url = reverse('classroom_exams:admin_review_exam', args=[obj.id])
            
            # Devolvemos un botón HTML bonito
            return format_html(
                '<a class="button" href="{}" target="_blank" style="background-color:#4299e1; color:white; padding:5px 10px; border-radius:4px; font-weight:bold;">Ver Examen</a>',
                url
            )
        return "-"
    
    # Nombre de la columna en el admin
    ver_examen_btn.short_description = "Revisión"
