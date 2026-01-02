## DFD Nivel 0: Diagrama de Contexto

```mermaid
graph LR
    %% --- ESTILOS ---
    classDef actor fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1;
    classDef system fill:#263238,stroke:#ffca28,stroke-width:3px,color:#ffffff;
    classDef external fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,stroke-dasharray: 5 5,color:#e65100;

    %% --- NODOS ---
    ALUMNO[👤 Alumno]:::actor
    DOCENTE[🎓 Docente]:::actor
    ADMIN[🛠️ Admin Tenant]:::actor
    IA_EXT[🤖 API Externa Gemini]:::external
    
    %% Nodo Central Redondo
    SYSTEM((💻 PLATAFORMA<br/>PROCTORING)):::system

    %% --- RELACIONES ---
    ALUMNO -->|1. Credenciales/Biometría| SYSTEM
    ALUMNO -->|2. Respuestas| SYSTEM
    SYSTEM -->|3. Feedback Examen| ALUMNO

    DOCENTE -->|4. Config Examen| SYSTEM
    SYSTEM -->|5. Alertas Riesgo| DOCENTE
    DOCENTE -->|6. Auditoría| SYSTEM

    ADMIN -->|7. Config Umbrales| SYSTEM
    SYSTEM -.->|8. Reportes| ADMIN

    SYSTEM -->|9. Imágenes| IA_EXT
    IA_EXT -.->|10. Validación JSON| SYSTEM
