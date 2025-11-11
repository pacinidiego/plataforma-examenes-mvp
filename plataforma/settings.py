"""
Configuración de Django para el proyecto Plataforma.
Sprint S0a: Setup de Arquitectura Core (Celery/Redis, R2)
Especificación: 18.2, 18.3, C4-4
"""

import os
from pathlib import Path
import dj_database_url # Render usa esto

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Clave secreta - ¡NO SUBIR A GIT PUBLICO CON LA CLAVE REAL!
# Render la sobrescribirá con una variable de entorno.
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-placeholder-key-s0a')

# DEBUG se debe poner en 'False' en producción
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

# Hosts permitidos. Render maneja esto, '*' es inseguro pero simple para el MVP.
ALLOWED_HOSTS = []
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# CSRF (Protección) - Necesario para que Render funcione
CSRF_TRUSTED_ORIGINS = [f"https://{RENDER_EXTERNAL_HOSTNAME}"] if RENDER_EXTERNAL_HOSTNAME else []


# Application definition
# (Spec 18.2)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles', # Para WhiteNoise
    
    # Apps de Terceros (S0a)
    'rest_framework',
    'storages', # Para R2/S3 (Spec 18.2)
    'django_celery_results', # (Spec 18.2)

    # Apps Propias (S0b)
    'tenancy.apps.TenancyConfig', # <-- ¡ESTA ES LA LÍNEA NUEVA!
    # Apps Propias (S1)
    'exams.apps.ExamsConfig', # <-- ¡AÑADE ESTA LÍNEA!
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Sirve estáticos en Render
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'plataforma.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'plataforma.wsgi.application'


# Database (Spec C4-4)
# Render nos da una DATABASE_URL
DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        ssl_require=True # Requerido por Render/Neon
    )
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# Configuración para WhiteNoise (Render)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ---> ¡LÍNEA CONFLICTIVA ELIMINADA! <---
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage' 
# Esta línea causaba el error "mutually exclusive". 
# La configuración correcta está abajo, dentro de STORAGES.


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- 1. Configuración de Celery (S0a / C4-4) ---
# (Spec 18.2)
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') # Viene de render.yaml
CELERY_RESULT_BACKEND = 'django-db' # Guarda resultados en la DB de Django (Postgres)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# --- 2. Configuración de Storage (S0a / R2 - C4-4) ---
# (Spec 18.2) Usamos Cloudflare R2 (compatible S3)
CLOUDFLARE_R2_ACCOUNT_ID = os.environ.get('CLOUDFLARE_R2_ACCOUNT_ID')
CLOUDFLARE_R2_ACCESS_KEY_ID = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID')
CLOUDFLARE_R2_SECRET_ACCESS_KEY = os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
CLOUDFLARE_R2_BUCKET_NAME = os.environ.get('CLOUDFLARE_R2_BUCKET_NAME')

if CLOUDFLARE_R2_ACCOUNT_ID:
    # Configuración de S3 (para Cloudflare R2)
    AWS_ACCESS_KEY_ID = CLOUDFLARE_R2_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = CLOUDFLARE_R2_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = CLOUDFLARE_R2_BUCKET_NAME
    AWS_S3_ENDPOINT_URL = f"https://{CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    
    # (Spec 14: Evidencias cifradas, pero R2 lo maneja server-side)
    AWS_DEFAULT_ACL = 'private' # (Spec 14: Privacidad)
    AWS_S3_FILE_OVERWRITE = False # (Spec 7: Resiliencia)
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_REGION_NAME = 'auto' # R2 usa 'auto'

    # Storage por defecto para todos los FileFields (Spec 18.2)
    # Todos los archivos subidos (ej. Evidencias) van a R2.
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    # Fallback si R2 no está configurado (desarrollo local)
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
