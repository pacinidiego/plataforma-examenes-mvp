from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import reverse
import csv
from .models import KioskConfig, KioskSession

# --- 1. Exportación CSV ---
def exportar_notas_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reporte_notas.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Nombre del Alumno', 'DNI', 'Nota Final', 'Fecha Inicio', 'Examen'])
    
    for sesion in queryset:
        writer.writerow([
            sesion.alumno_nombre,
            sesion.alumno_dni,
            sesion.nota_final,
            sesion.fecha_inicio.strftime("%Y-%m-%d %H:%M") if sesion.fecha_inicio else '-',
            sesion.config.nombre
        ])
        
    return response

exportar_notas_csv.short_description = "Descargar notas seleccionadas (CSV)"


# --- 2. Configuraciones (Config del Examen) ---

@admin.register(KioskConfig)
class KioskConfigAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tenant', 'duracion_minutos', 'activo', 'btn_pdf')
    list_filter = ('tenant', 'activo')
    search_fields = ('nombre',)

    # --- CAMBIO: SELECT DESPLEGABLE ---
    def btn_pdf(self, obj):
        try:
            url_base = reverse('classroom_exams:pdf_variantes', args=[obj.id])
            
            # Construimos las opciones del 1 al 10 dinámicamente
            options_html = ""
            for i in range(1, 11):
                options_html += f'<option value="{i}">{i} Temas</option>'

            # Creamos el HTML del Select
            # El evento 'onchange' detecta cuando eliges una opción y redirige
            html = f"""
            <select onchange="if(this.value) window.location.href='{url_base}?cantidad=' + this.value;" 
                    style="cursor: pointer; padding: 5px; border-radius: 4px; border: 1px solid #ccc; background-color: #fff; color: #333; font-weight: bold;">
                <option value="" selected disabled>🖨️ Generar PDF...</option>
                {options_html}
            </select>
            """
            return format_html(html)
        except Exception:
            return "-"

    btn_pdf.short_description = "Descargar Examen"


# --- 3. Sesiones (Alumnos rindiendo) ---

@admin.register(KioskSession)
class KioskSessionAdmin(admin.ModelAdmin):
    list_display = ('alumno_nombre', 'alumno_dni', 'nota_final', 'fecha_inicio', 'examen_nombre', 'ver_examen_btn')
    list_filter = ('config', 'fecha_inicio')
    search_fields = ('alumno_nombre', 'alumno_dni')
    actions = [exportar_notas_csv]

    def examen_nombre(self, obj):
        return obj.config.nombre
    examen_nombre.short_description = 'Examen'

    def ver_examen_btn(self, obj):
        if obj.examen_snapshot:
            url = reverse('classroom_exams:admin_review_exam', args=[obj.id])
            return format_html(
                '<a class="button" href="{}" target="_blank" style="background-color:#4299e1; color:white; padding:4px 8px; border-radius:4px; font-weight:bold; font-size:11px;">Ver Examen</a>',
                url
            )
        return "-"
    
    ver_examen_btn.short_description = "Revisión"
