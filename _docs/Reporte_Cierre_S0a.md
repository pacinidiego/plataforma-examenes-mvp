Reporte de Cierre de Sprint: S0a
Proyecto: Plataforma de Exámenes (MVP)
Sprint: S0a — Infra & PoC Tortura
Fechas del Sprint (Planificadas): 10/11/2025 – 21/11/2025
Fecha de Cierre (Real): 10/11/2025
Estado: COMPLETADO (Adelantado)
1. Resumen Ejecutivo
El Sprint S0a se ha completado con éxito, cumpliendo el 100% de los Criterios de Aceptación (DoD) definidos en la especificación (Sección 20.1 y Anexo A).
Los dos objetivos principales del sprint se han alcanzado:
1.	Setup de Arquitectura Core: La infraestructura C4-4 (Web, Worker, DB, Redis, R2) está desplegada en Render, conectada y "Live".
2.	PoC "Prototipo de Tortura": Las APIs de navegador de alto riesgo (Cámara, Mic, IA, Fullscreen, Snapshot) han sido validadas exitosamente en un entorno de prueba.
El Gate-0 se declara SUPERADO. El Buffer de Mitigación PoC (1 sem) no es necesario, permitiendo que el proyecto continúe al S0b según el cronograma.
2. Pista 1: Setup de Arquitectura Core (Render)
Objetivo: Desplegar la arquitectura de backend (C4-4) en el hosting MVP.
Estado: COMPLETADO
2.1. Despliegue de Servicios
Los 4 servicios del render.yaml están desplegados y "Live":
•	plataforma-db (PostgreSQL): Live
•	plataforma-redis (Redis): Live
•	plataforma-web (Django/Gunicorn): Live
•	plataforma-worker (Celery): Live
2.2. Evidencia de Pruebas (Endpoints)
La aplicación plataforma-web responde correctamente en su URL pública de producción:
https://plataforma-web-xzkr.onrender.com
•	Prueba de Health Check (/health/): Éxito.
o	Evidencia: image_4372e3.png (Muestra "OK: Web Service (S0a) está activo.")
•	Prueba de Admin Django (/admin/): Éxito.
o	Evidencia: image_43735e.png (Muestra la página de login de "Administración de Django".)
3. Pista 2: PoC "Prototipo de Tortura" (Anexo A)
Objetivo: Validar la viabilidad técnica de las APIs del Runner en el navegador.
Estado: COMPLETADO
3.1. Despliegue del PoC
El PoC (poc-tortura.html) está desplegado y accesible vía GitHub Pages.
•	URL de Prueba: https://pacinidiego.github.io/plataforma-examenes-mvp/poc-tortura.html
3.2. Evidencia de Pruebas (Criterios de Aceptación - DoD)
Las pruebas realizadas (evidenciadas en las capturas) confirman el éxito de los DoD del Anexo A:
•	Permisos de Cámara/Mic (getUserMedia): Éxito.
o	Evidencia: image_43df81.png (Muestra el diálogo de permisos del navegador).
•	Detección Facial (MediaPipe): Éxito.
o	Evidencia: image_43e31d.png (Muestra el tick verde en "Detección Facial").
o	Evidencia: image_43e33c.png (Muestra el log Resultado IA: Caras detectadas: 1).
•	Detección de Audio (VAD): Éxito.
o	Evidencia: image_43e31d.png (Muestra el tick verde en "Detección de Audio (VAD)").
•	API de Visibilidad (Focus): Éxito.
o	Evidencia: image_43e31d.png (Muestra el tick verde en "API de Visibilidad").
•	API de Pantalla Completa: Éxito.
o	Evidencia: image_43e33c.png (Muestra el log Estado Fullscreen: ON).
•	Snapshot DOM (html2canvas): Éxito.
o	Evidencia: poc_tortura_snapshot.jpg (Muestra el snapshot generado por el PoC).
•	Performance (CPU): Éxito.
o	Evidencia: image_43e31d.png (Muestra el tick verde en "Performance (CPU ≤ 25%)").
o	Evidencia: image_43e33c.png (Muestra el log Costo JS: 0.00 ms).
4. Veredicto y Próximos Pasos
•	Veredicto Gate-0: SUPERADO.
•	Próximo Sprint: S0b - Platform SA Console (Inicio: 11/11/2025).

