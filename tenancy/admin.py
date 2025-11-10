from django.contrib import admin
from .models import Tenant, TenantMembership

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """
    Define cómo se ven los Tenants en el panel de admin.
    """
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    """
    Define cómo se ven las Membresías (Roles) en el panel de admin.
    """
    list_display = ('user', 'tenant', 'role', 'legajo')
    list_filter = ('tenant', 'role')
    search_fields = ('user__username', 'user__email', 'tenant__name', 'legajo')
    
    # Esto añade un buscador de usuarios en lugar de un dropdown (para miles de usuarios)
    raw_id_fields = ('user',)
