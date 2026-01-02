## DFD Nivel 1: Desglose de Subsistemas

Este diagrama detalla cómo fluye la información entre los cuatro módulos principales del sistema (Tenancy, Backoffice, Runner y Scoring).

```mermaid
graph LR
    %% --- ESTILOS (CSS) ---
    classDef actor fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1;
    classDef process fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;
    classDef db fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef external fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,stroke-dasharray: 5 5,color:#e65100;

    %% --- ACTORES EXTERNOS ---
    ADMIN[🛠️ Admin Tenant]:::actor
    DOCENTE[🎓 Docente]:::actor
    ALUMNO[👤 Alumno]:::actor
    IA[🤖 Gemini API]:::external

    %% --- SUBSISTEMA INTERNO ---
    subgraph SYSTEM [PLATAFORMA INTERNA]
        direction TB
        
        %% Procesos
        P1(1.0 GESTIÓN TENANTS):::process
        P2(2.0 BACKOFFICE):::process
        P3(3.0 RUNNER):::process
        P4(4.0 SCORING & AUDITORÍA):::process

        %% Bases de Datos
        D1[(🗄️ DB: Tenants)]:::db
        D2[(🗄️ DB: Exámenes)]:::db
        D3[(🗄️ DB: Logs/Intentos)]:::db
    end

    %% --- FLUJOS DE CONFIGURACIÓN ---
    ADMIN -->|Configura Umbrales| P1
    P1 -->|Guarda| D1
    
    %% --- FLUJOS DE CREACIÓN ---
    DOCENTE -->|Crea Examen| P2
    P2 -->|Guarda Items| D2
    D1 -.->|Valida Permisos| P2

    %% --- FLUJOS DE EJECUCIÓN ---
    ALUMNO -->|Ingresa| P3
    D2 -.->|Carga Preguntas| P3
    P3 <-->|Valida Imagen| IA
    P3 -->|Guarda Eventos| D3

    %% --- FLUJOS DE AUDITORÍA (LO QUE HICIMOS HOY) ---
    D1 -.->|Lee Reglas Semáforo| P4
    D3 -.->|Lee Evidencia| P4
    D2 -.->|Lee Respuestas Correctas| P4
    
    P4 -->|Dashboard Riesgo| DOCENTE
    DOCENTE -->|Acción: Validar/Anular| P4
    P4 -->|Actualiza Nota| D3
