# Documentación de Arquitectura del Sistema

Esta sección describe el flujo de datos y la arquitectura de la plataforma de proctoring.

## DFD Nivel 0: Diagrama de Contexto
Visión general de cómo interactúa la plataforma con los actores externos.

```mermaid
graph TD
    %% ENTIDADES EXTERNAS
    ALUMNO[👤 Alumno]
    DOCENTE[🎓 Docente]
    ADMIN[🛠️ Admin Tenant]
    IA_EXT[🤖 API Externa Gemini]

    %% PROCESO CENTRAL
    SYSTEM((💻 PLATAFORMA PROCTORING))

    %% FLUJOS
    ALUMNO -->|1. Credenciales y Biometría| SYSTEM
    ALUMNO -->|2. Respuestas de Examen| SYSTEM
    SYSTEM -->|3. Interfaz de Examen y Feedback| ALUMNO

    DOCENTE -->|4. Config. Examen| SYSTEM
    DOCENTE -->|5. Auditoría y Notas| SYSTEM
    SYSTEM -->|6. Alertas de Riesgo| DOCENTE

    ADMIN -->|7. Config. Umbrales Riesgo| SYSTEM
    SYSTEM -->|8. Reportes| ADMIN

    SYSTEM -->|9. Imágenes| IA_EXT
    IA_EXT -->|10. Validación JSON| SYSTEM
