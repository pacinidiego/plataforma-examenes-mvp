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
    # Agregamos 'btn_pdf' a la lista
    list_display = ('nombre', 'tenant', 'duracion_minutos', 'activo', 'btn_pdf')
    list_filter = ('tenant', 'activo')
    search_fields = ('nombre',)

    # --- FUNCIÓN QUE CREA LOS BOTONES MULTI-TEMA ---
    def btn_pdf(self, obj):
        try:
            # Obtenemos la URL base (sin parámetros)
            url_base = reverse('classroom_exams:pdf_variantes', args=[obj.id])
            
            # Estilos CSS para que los botones se vean bonitos y compactos
            style_base = "color:white; padding: 2px 6px; border-radius: 3px; font-weight: bold; text-decoration: none; margin-right: 4px; font-size: 11px;"
            style_2 = f"background-color:#48bb78; {style_base}" # Verde (2 Temas)
            style_3 = f"background-color:#4299e1; {style_base}" # Azul (3 Temas)
            style_4 = f"background-color:#ed8936; {style_base}" # Naranja (4 Temas)

            # Creamos el HTML con 3 enlaces distintos
            html = f"""
            <div style="display:flex; align-items:center;">
                <span style="margin-right:5px; color:#666; font-size:11px;">PDF:</span>
                <a href="{url_base}?cantidad=2" style="{style_2}" title="Generar 2 Temas">2</a>
                <a href="{url_base}?cantidad=3" style="{style_3}" title="Generar 3 Temas">3</a>
                <a href="{url_base}?cantidad=4" style="{style_4}" title="Generar 4 Temas">4</a>
            </div>
            """
            return format_html(html)
        except Exception:
            return "-"

    btn_pdf.short_description = "Descargar Variantes"


@admin.register(KioskSession)
class KioskSessionAdmin(admin.ModelAdmin):
    list_display = ('alumno_nombre', 'alumno_dni', 'nota_final', 'fecha_inicio', 'examen_nombre', 'ver_examen_btn')
    
    list_filter = ('config', 'fecha_inicio')
    search_fields = ('alumno_nombre', 'alumno_dni')
    actions = [exportar_notas_csv]

    def examen_nombre(self, obj):
        return obj.config.nombre
    examen_nombre.short_description = 'Examen'

    # --- FUNCIÓN QUE CREA EL BOTÓN VER REVISIÓN ---
    def ver_examen_btn(self, obj):
        if obj.examen_snapshot:
            url = reverse('classroom_exams:admin_review_exam', args=[obj.id])
            
            return format_html(
                '<a class="button" href="{}" target="_blank" style="background-color:#4299e1; color:white; padding:4px 8px; border-radius:4px; font-weight:bold; font-size:11px;">Ver Examen</a>',
                url
            )
        return "-"
    
    ver_examen_btn.short_description = "Revisión"
