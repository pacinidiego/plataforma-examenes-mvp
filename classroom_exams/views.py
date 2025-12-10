import random
from django.shortcuts import render, redirect, get_object_or_404
from .models import KioskConfig, KioskSession
from exams.models import Item  # Importamos tus preguntas

def generar_examen(config):
    """
    Esta función es el 'Motor' que selecciona las preguntas al azar.
    Retorna una lista de diccionarios con la estructura del examen.
    """
    items_seleccionados = []
    
    # 1. Buscamos preguntas por dificultad en el Banco del Tenant
    # Asumimos valores: 1=Easy, 2=Medium, 3=Hard (según tu modelo Item)
    pool_faciles = list(Item.objects.filter(tenant=config.tenant, difficulty=1))
    pool_medias = list(Item.objects.filter(tenant=config.tenant, difficulty=2))
    pool_dificiles = list(Item.objects.filter(tenant=config.tenant, difficulty=3))

    # 2. Seleccionamos al azar (asegurando no fallar si hay pocas)
    # Si pides 5 fáciles pero hay 2, toma las 2.
    seleccion_faciles = random.sample(pool_faciles, min(len(pool_faciles), config.cantidad_faciles))
    seleccion_medias = random.sample(pool_medias, min(len(pool_medias), config.cantidad_medias))
    seleccion_dificiles = random.sample(pool_dificiles, min(len(pool_dificiles), config.cantidad_dificiles))

    todos_items = seleccion_faciles + seleccion_medias + seleccion_dificiles
    random.shuffle(todos_items) # Mezclamos para que no salgan ordenadas por dificultad

    # 3. Construimos el "Snapshot" (La foto del examen)
    examen_data = []
    for item in todos_items:
        # Mezclamos las opciones (respuestas)
        opciones = item.options or [] # Asumimos que es una lista de dicts: [{'text':'A',...}]
        random.shuffle(opciones)
        
        # Guardamos solo lo necesario para rendir
        pregunta_struct = {
            "id": item.id,
            "texto": item.stem,
            "opciones": opciones, # Ya mezcladas
            "tipo": item.item_type
        }
        examen_data.append(pregunta_struct)
    
    return examen_data

# --- VISTAS ---

def acceso_alumno(request):
    config = KioskConfig.objects.filter(activo=True).first()
    
    if not config:
        return render(request, 'classroom_exams/error_no_examen.html', {'mensaje': "No hay examen activo."})

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        dni = request.POST.get('dni')

        if nombre and dni:
            # 1. Generamos las preguntas AL VUELO
            snapshot = generar_examen(config)
            
            # 2. Creamos la sesión guardando ese snapshot
            sesion = KioskSession.objects.create(
                config=config,
                alumno_nombre=nombre,
                alumno_dni=dni,
                examen_snapshot=snapshot  # <--- Aquí guardamos el examen único
            )
            
            # 3. Guardamos ID en sesión y redirigimos a rendir
            request.session['kiosk_session_id'] = sesion.id
            return redirect('classroom_exams:rendir_examen') 
            
    return render(request, 'classroom_exams/acceso.html', {'examen': config})

def rendir_examen(request):
    # Verificamos seguridad
    sesion_id = request.session.get('kiosk_session_id')
    if not sesion_id:
        return redirect('classroom_exams:acceso')

    sesion = get_object_or_404(KioskSession, id=sesion_id)
    
    # Si ya terminó, no dejar entrar de nuevo (Opcional por ahora)
    # if sesion.fecha_fin:
    #     return redirect('classroom_exams:resultado')

    # Pasamos las preguntas a la plantilla
    preguntas = sesion.examen_snapshot
    
    if request.method == 'POST':
        # Aquí procesaremos las respuestas más adelante
        pass

    return render(request, 'classroom_exams/hoja_examen.html', {
        'sesion': sesion,
        'preguntas': preguntas
    })
