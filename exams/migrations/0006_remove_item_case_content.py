# exams/migrations/0006_remove_item_case_content.py
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0005_remove_item_case_content'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='item',
            name='case_content',
        ),
    ]
