import random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import KioskConfig, KioskSession
from exams.models import Item

# --- FUNCIONES AUXILIARES ---

def generar_examen(config):
    # (Esta función queda igual que antes)
    items_seleccionados = []
    pool_faciles = list(Item.objects.filter(tenant=config.tenant, difficulty=1))
    pool_medias = list(Item.objects.filter(tenant=config.tenant, difficulty=2))
    pool_dificiles = list(Item.objects.filter(tenant=config.tenant, difficulty=3))

    seleccion_faciles = random.sample(pool_faciles, min(len(pool_faciles), config.cantidad_faciles))
    seleccion_medias = random.sample(pool_medias, min(len(pool_medias), config.cantidad_medias))
    seleccion_dificiles = random.sample(pool_dificiles, min(len(pool_dificiles), config.cantidad_dificiles))

    todos_items = seleccion_faciles + seleccion_medias + seleccion_dificiles
    random.shuffle(todos_items)

    examen_data = []
    for item in todos_items:
        opciones = item.options or [] 
        random.shuffle(opciones)
        pregunta_struct = {
            "id": item.id,
            "texto": item.stem,
            "opciones": opciones,
            "tipo": item.item_type,
            "respuesta_alumno": None, # Nuevo campo
            "es_correcta": False      # Nuevo campo
        }
        examen_data.append(pregunta_struct)
    
    return examen_data

def calcular_nota(sesion, datos_post):
    """Calcula la nota y actualiza el snapshot con las respuestas del alumno"""
    preguntas = sesion.examen_snapshot
    respuestas_correctas = 0
    total_preguntas = len(preguntas)

    for p in preguntas:
        # Obtenemos qué respondió el alumno (el ID o texto de la opción)
        respuesta_id = datos_post.get(f'pregunta_{p["id"]}')
        p['respuesta_alumno'] = respuesta_id
        
        # Verificamos si es correcta
        # Buscamos la opción en la lista de opciones de esa pregunta
        opcion_elegida = next((op for op in p['opciones'] if str(op.get('id', op.get('text'))) == str(respuesta_id)), None)
        
        if opcion_elegida and opcion_elegida.get('correct') is True:
            p['es_correcta'] = True
            respuestas_correctas += 1
        else:
            p['es_correcta'] = False
            
    # Calculamos nota del 1 al 10
    if total_preguntas > 0:
        nota = (respuestas_correctas / total_preguntas) * 10
    else:
        nota = 0
        
    sesion.examen_snapshot = preguntas
    sesion.nota_final = round(nota, 2)
    sesion.save()

# --- VISTAS ---

def acceso_alumno(request):
    # Limpiamos sesión anterior por seguridad si entran directo
    if 'kiosk_session_id' in request.session:
        del request.session['kiosk_session_id']
        
    config = KioskConfig.objects.filter(activo=True).first()
    if not config:
        return render(request, 'classroom_exams/error_no_examen.html', {'mensaje': "No hay examen activo."})

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        dni = request.POST.get('dni')
        if nombre and dni:
            snapshot = generar_examen(config)
            sesion = KioskSession.objects.create(
                config=config,
                alumno_nombre=nombre,
                alumno_dni=dni,
                examen_snapshot=snapshot
            )
            request.session['kiosk_session_id'] = sesion.id
            return redirect('classroom_exams:rendir_examen') 
            
    return render(request, 'classroom_exams/acceso.html', {'examen': config})

def rendir_examen(request):
    sesion_id = request.session.get('kiosk_session_id')
    if not sesion_id:
        return redirect('classroom_exams:acceso')

    sesion = get_object_or_404(KioskSession, id=sesion_id)
    
    # Si ya tiene nota, lo mandamos al resultado (evita volver atrás y rendir de nuevo)
    if sesion.nota_final is not None:
         return redirect('classroom_exams:resultado_examen')

    if request.method == 'POST':
        # 1. Calculamos la nota
        calcular_nota(sesion, request.POST)
        # 2. Redirigimos a la pantalla de resultados
        return redirect('classroom_exams:resultado_examen')

    return render(request, 'classroom_exams/hoja_examen.html', {
        'sesion': sesion,
        'preguntas': sesion.examen_snapshot
    })

def resultado_examen(request):
    """Pantalla congelada con la nota y opciones para el profesor"""
    sesion_id = request.session.get('kiosk_session_id')
    if not sesion_id:
        return redirect('classroom_exams:acceso')
        
    sesion = get_object_or_404(KioskSession, id=sesion_id)
    
    return render(request, 'classroom_exams/resultado.html', {'sesion': sesion})

def accion_profesor(request):
    """Verifica el PIN y ejecuta Reinicio o Revisión"""
    sesion_id = request.session.get('kiosk_session_id')
    sesion = get_object_or_404(KioskSession, id=sesion_id)
    
    if request.method == 'POST':
        pin_ingresado = request.POST.get('pin')
        accion = request.POST.get('accion') # 'reiniciar' o 'revisar'
        
        # Verificamos PIN contra la config
        if pin_ingresado == sesion.config.pin_profesor:
            if accion == 'reiniciar':
                request.session.flush() # Borramos todo
                return redirect('classroom_exams:acceso')
            elif accion == 'revisar':
                # Mostramos el examen corregido (usamos el mismo template pero con flag)
                return render(request, 'classroom_exams/hoja_examen.html', {
                    'sesion': sesion,
                    'preguntas': sesion.examen_snapshot,
                    'modo_revision': True
                })
        else:
            messages.error(request, "PIN Incorrecto")
            
    return redirect('classroom_exams:resultado_examen')
