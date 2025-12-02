# runner/migrations/0001_initial.py
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('exams', '0006_remove_item_case_content'),
    ]

    operations = [
        # 1. Tabla de Intentos (El Examen)
        migrations.CreateModel(
            name='Attempt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('student_name', models.CharField(blank=True, max_length=255, verbose_name='Nombre del Alumno')),
                ('student_legajo', models.CharField(blank=True, max_length=100, verbose_name='Legajo/DNI')),
                ('start_time', models.DateTimeField(auto_now_add=True, verbose_name='Inicio')),
                ('end_time', models.DateTimeField(blank=True, null=True, verbose_name='Fin')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='Completado el')),
                ('last_heartbeat', models.DateTimeField(auto_now=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('answers', models.JSONField(blank=True, default=dict)),
                ('score', models.FloatField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='exams.exam')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-start_time'],
            },
        ),
        # 2. Tabla de Eventos (La Seguridad / Caja Negra)
        migrations.CreateModel(
            name='AttemptEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('event_type', models.CharField(choices=[('SESSION_RESUME', 'Reconexión / Reanudación'), ('FOCUS_LOST', 'Pérdida de Foco (Cambio de Pestaña)'), ('FULLSCREEN_EXIT', 'Salida de Pantalla Completa'), ('MULTI_FACE', 'Múltiples rostros detectados'), ('NO_FACE', 'Rostro no detectado'), ('AUDIO_SPIKE', 'Sonido/Voz detectada')], max_length=50)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('evidence_url', models.URLField(blank=True, null=True)),
                ('attempt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='runner.attempt')),
            ],
            options={
                'ordering': ['timestamp'],
            },
        ),
    ]
