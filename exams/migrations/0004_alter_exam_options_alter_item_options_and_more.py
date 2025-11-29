# exams/migrations/0004_alter_exam_options_alter_item_options_and_more.py
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0003_exam_status_access_code'),
        ('tenancy', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Agregamos los campos de tiempo (TI-01 y TI-02)
        migrations.AddField(
            model_name='exam',
            name='extra_time_buffer',
            field=models.PositiveIntegerField(default=5, help_text='Tiempo adicional global para el examen.', verbose_name='Buffer extra (minutos)'),
        ),
        migrations.AddField(
            model_name='exam',
            name='time_per_item',
            field=models.PositiveIntegerField(default=60, help_text='Tiempo límite para cada pregunta individual.', verbose_name='Segundos por pregunta'),
        ),
        # Ajustes de configuración de campos (para sincronizar con tu models.py actual)
        migrations.AlterField(
            model_name='examitemlink',
            name='points',
            field=models.FloatField(default=1.0, verbose_name='Puntaje'),
        ),
    ]
