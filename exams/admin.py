from django.contrib import admin
from .models import Item, Exam, ExamItemLink

class ExamItemInline(admin.TabularInline):
    """
    Permite agregar Ítems directamente DENTRO del formulario del Examen.
    Este es el "Constructor" (Spec S1) en el admin.
    """
    model = ExamItemLink
    raw_id_fields = ('item',) # Usa un buscador para los ítems, no un dropdown
    extra = 1
    ordering = ('order',)

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('stem', 'item_type', 'tenant', 'author', 'difficulty', 'created_at')
    list_filter = ('tenant', 'item_type', 'difficulty')
    search_fields = ('stem', 'tags', 'tenant__name')
    # Oculta campos que no aplican según el tipo de ítem (esto requiere JS, lo dejamos para después)
    # ...

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'tenant', 'author', 'created_at')
    list_filter = ('tenant',)
    search_fields = ('title', 'tenant__name')
    
    # Aquí está la magia del "Constructor" (S1):
    inlines = [ExamItemInline]
