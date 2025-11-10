"""
Configuración de la app de Celery para plataforma.
Sprint S0a: Setup de Arquitectura Core
Especificación: 18.2
"""

import os
from celery import Celery

# Apuntar a la configuración de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plataforma.settings')

app = Celery('plataforma')

# Usar la configuración de django (prefijo 'CELERY_')
# (Lee CELERY_BROKER_URL y CELERY_RESULT_BACKEND de settings.py)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descubrir tareas automáticamente en todas las apps de Django
# (Buscará archivos tasks.py en el futuro)
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    """
    Tarea de debug para S0a.
    Permite verificar que el worker (C4-4) está vivo y 
    conectado a Redis y Postgres.
    """
    print(f'Request: {self.request!r}')
    log_message = "Tarea de debug de Celery (S0a) ejecutada."
    print(log_message)
    return log_message
