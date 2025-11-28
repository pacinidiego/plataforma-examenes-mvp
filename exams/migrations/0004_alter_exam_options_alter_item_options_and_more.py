# exams/migrations/0004_alter_exam_options_alter_item_options_and_more.py

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0003_exam_status_access_code'),
        ('tenancy', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='exam',
            options={'ordering': ['-created_at'], 'verbose_name': 'Examen', 'verbose_name_plural': 'Exámenes'},
        ),
        migrations.AlterModelOptions(
            name='item',
            options={'verbose_name': 'Pregunta (Item)', 'verbose_name_plural': 'Banco de Preguntas'},
        ),
        # === AQUI QUITAMOS EL REMOVE FIELD QUE DABA ERROR ===
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
        migrations.AlterField(
            model_name='exam',
            name='author',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='exam',
            name='items',
            field=models.ManyToManyField(related_name='exams', through='exams.ExamItemLink', to='exams.item'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='shuffle_items',
            field=models.BooleanField(default=True, verbose_name='Mezclar preguntas'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='shuffle_options',
            field=models.BooleanField(default=True, verbose_name='Mezclar opciones'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exams', to='tenancy.tenant'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='title',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='examitemlink',
            name='order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='examitemlink',
            name='points',
            field=models.FloatField(default=1.0, verbose_name='Puntaje'),
        ),
        migrations.AlterField(
            model_name='item',
            name='author',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='item',
            name='difficulty',
            field=models.IntegerField(choices=[(1, 'Fácil'), (2, 'Media'), (3, 'Difícil')], default=2),
        ),
        migrations.AlterField(
            model_name='item',
            name='item_type',
            field=models.CharField(choices=[('MC', 'Opción Múltiple (MC)'), ('SA', 'Respuesta Corta (SA)'), ('ES', 'Ensayo (ES)')], default='MC', max_length=2),
        ),
        migrations.AlterField(
            model_name='item',
            name='options',
            field=models.JSONField(blank=True, help_text="Opciones para MC (ej. [{'text': 'A', 'correct': True}, ...])", null=True),
        ),
        migrations.AlterField(
            model_name='item',
            name='tags',
            field=models.CharField(blank=True, help_text='Etiquetas separadas por comas', max_length=255),
        ),
        migrations.AlterField(
            model_name='item',
            name='tenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='tenancy.tenant'),
        ),
    ]
