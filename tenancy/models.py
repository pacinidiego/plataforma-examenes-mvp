from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

# (Spec 3 y 4)
class Tenant(models.Model):
    """
    Representa una institución (ej. "Universidad de Prueba").
    (Spec 4: Multi-tenant y gobierno)
    """
    name = models.CharField(max_length=255, unique=True, verbose_name="Nombre de la Institución")
    created_at = models.DateTimeField(auto_now_add=True)
    # (Aquí irán los toggles y planes del S5b/S6)
    
    class Meta:
        verbose_name = _("Institución (Tenant)")
        verbose_name_plural = _("Instituciones (Tenants)")

    def __str__(self):
        return self.name

class TenantMembership(models.Model):
    """
    Define el ROL de un Usuario dentro de un Tenant.
    (Spec 3: Roles)
    """
    # (Roles de Spec 3)
    ROLE_ADMIN = 'admin'
    ROLE_DOCENTE = 'docente'
    ROLE_AUXILIAR = 'auxiliar'
    ROLE_ALUMNO = 'alumno'
    ROLE_CHOICES = [
        (ROLE_ADMIN, _('Admin del Tenant')),
        (ROLE_DOCENTE, _('Docente')),
        (ROLE_AUXILIAR, _('Auxiliar/Corrector')),
        (ROLE_ALUMNO, _('Alumno')),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="tenant_memberships",
        verbose_name=_("Usuario")
    )
    tenant = models.ForeignKey(
        Tenant, 
        on_delete=models.CASCADE, 
        related_name="memberships",
        verbose_name=_("Institución")
    )
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        verbose_name=_("Rol")
    )
    
    # (Campos de Identidad de Spec 5)
    legajo = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        db_index=True, 
        verbose_name=_("Legajo")
    )
    dni_hash = models.CharField(
        max_length=256, 
        blank=True, 
        null=True, 
        db_index=True, 
        verbose_name=_("DNI Hash (SHA-256)")
    )

    class Meta:
        # Un usuario solo puede tener un rol por tenant
        unique_together = ('user', 'tenant') 
        verbose_name = _("Membresía de Institución")
        verbose_name_plural = _("Membresías de Institución")

    def __str__(self):
        return f"{self.user.username} es {self.get_role_display()} en {self.tenant.name}"
