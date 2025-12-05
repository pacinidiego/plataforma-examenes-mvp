from django.contrib import admin
from .models import Attempt, AttemptEvent

@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'exam', 'student_name', 'start_time', 'score', 'is_active')
    list_filter = ('exam', 'is_active', 'start_time')
    search_fields = ('student_name', 'student_legajo', 'id')

@admin.register(AttemptEvent)
class AttemptEventAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'event_type', 'attempt')
    list_filter = ('event_type',)
