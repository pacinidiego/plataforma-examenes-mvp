# Esto le dice a Django cómo encontrar la app de Celery
from .celery import app as celery_app

__all__ = ('celery_app',)
