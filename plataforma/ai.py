"""
Cliente de IA compartido — usa OpenRouter (mismo stack que XARA, ../xara).

Reemplaza la integración anterior con Google Gemini. OpenRouter expone una API
compatible con OpenAI, así que usamos el SDK oficial `openai` apuntando a su
gateway. Los modelos se eligen acá: cambiarlos es una sola línea.
"""
import os

from openai import OpenAI

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

# --- Modelos (elegidos por tarea, los que mejor se adaptan) ---
# Texto / JSON estructurado: barato y muy bueno siguiendo instrucciones de formato.
CHAT_MODEL = "deepseek/deepseek-chat"
# Visión / OCR de documentos: fuerte leyendo texto en imágenes (igual que XARA).
VISION_MODEL = "qwen/qwen2.5-vl-72b-instruct"
# Fallback de visión si el principal falla o está saturado.
VISION_FALLBACK_MODEL = "google/gemini-2.5-flash"

# El cliente es None si no hay API key: cada vista hace el chequeo y degrada
# a "simulación / IA no configurada" en vez de romper.
client = None
if OPENROUTER_API_KEY:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={"X-Title": "Plataforma Examenes"},
    )


def strip_fences(text):
    """Quita los ```json ... ``` que algunos modelos agregan alrededor del JSON."""
    return (text or "").replace("```json", "").replace("```", "").strip()
