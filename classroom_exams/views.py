from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import KioskConfig, KioskSession
from exams.models import Item
import random

# --- FUNCIONES AUXILIARES ---

def generar_examen(config):
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
            "respuesta_alumno": None,
            "es_correcta": False
        }
        examen_data.append(pregunta_struct)
    
    return examen_data

def calcular_nota(sesion, datos_post):
    """Calcula la nota y actualiza el snapshot con las respuestas del alumno"""
    preguntas = sesion.examen_snapshot
    respuestas_correctas = 0
    total_preguntas = len(preguntas)

    for p in preguntas:
        # Obtenemos qué respondió el alumno
        respuesta_id = datos_post.get(f'pregunta_{p["id"]}')
        p['respuesta_alumno'] = respuesta_id
        
        # Verificamos si es correcta
        opcion_elegida = next((op for op in p['opciones'] if str(op.get('id', op.get('text'))) == str(respuesta_id)), None)
        
        if opcion_elegida and opcion_elegida.get('correct') is True:
            p['es_correcta'] = True
            respuestas_correctas += 1
        else:
            p['es_correcta'] = False
            
    if total_preguntas > 0:
        nota = (respuestas_correctas / total_preguntas) * 10
    else:
        nota = 0
        
    sesion.examen_snapshot = preguntas
    sesion.nota_final = round(nota, 2)
    sesion.save()

# --- VISTAS ---

def acceso_alumno(request):
    request.session.flush() # Limpieza total al entrar
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
                examen_snapshot=snapshot,
                indice_pregunta_actual=1 # Empezamos en la 1
            )
            request.session['kiosk_session_id'] = sesion.id
            # Vamos a las reglas
            return redirect('classroom_exams:instrucciones') 
            
    return render(request, 'classroom_exams/acceso.html', {'examen': config})

def instrucciones_examen(request):
    sesion_id = request.session.get('kiosk_session_id')
    if not sesion_id: return redirect('classroom_exams:acceso')
    sesion = get_object_or_404(KioskSession, id=sesion_id)

    if request.method == 'POST':
        # AQUÍ EMPIEZA EL TIEMPO REALMENTE
        sesion.fecha_inicio = timezone.now()
        sesion.save()
        return redirect('classroom_exams:rendir_examen')

    return render(request, 'classroom_exams/reglas.html', {'sesion': sesion})

def rendir_examen(request):
    sesion_id = request.session.get('kiosk_session_id')
    if not sesion_id: return redirect('classroom_exams:acceso')
    sesion = get_object_or_404(KioskSession, id=sesion_id)
    
    # 1. Seguridad: Si no aceptó las reglas (no tiene fecha inicio), volver a reglas
    if not sesion.fecha_inicio:
        return redirect('classroom_exams:instrucciones')

    # 2. Seguridad: Si ya terminó, al resultado
    if sesion.nota_final is not None:
         return redirect('classroom_exams:resultado_examen')

    # 3. Control de Tiempo
    duracion = sesion.config.duracion_minutos
    hora_fin = sesion.fecha_inicio + timedelta(minutes=duracion)
    tiempo_restante = (hora_fin - timezone.now()).total_seconds()
    
    if tiempo_restante <= 0:
        calcular_nota(sesion, {}) 
        return redirect('classroom_exams:resultado_examen')

    # 4. Obtener la pregunta CORRECTA
    idx = sesion.indice_pregunta_actual
    preguntas = sesion.examen_snapshot
    total = len(preguntas)
    
    # Validación de índice
    if idx > total:
        return redirect('classroom_exams:resultado_examen')

    pregunta_actual = preguntas[idx - 1]

    if request.method == 'POST':
        respuesta = request.POST.get(f'pregunta_{pregunta_actual["id"]}')
        
        # Guardamos respuesta
        pregunta_actual['respuesta_alumno'] = respuesta
        sesion.examen_snapshot = preguntas
        
        # AVANZAMOS EL ÍNDICE
        if idx < total:
            sesion.indice_pregunta_actual = idx + 1
            sesion.save()
            return redirect('classroom_exams:rendir_examen')
        else:
            # Fin del examen: Calcular nota
            respuestas_full = {}
            for p in preguntas:
                 if p.get('respuesta_alumno'):
                    respuestas_full[f'pregunta_{p["id"]}'] = p['respuesta_alumno']
            
            calcular_nota(sesion, respuestas_full)
            return redirect('classroom_exams:resultado_examen')

    return render(request, 'classroom_exams/hoja_examen.html', {
        'sesion': sesion,
        'pregunta': pregunta_actual,
        'indice_actual': idx,
        'total_preguntas': total,
        'tiempo_restante': int(tiempo_restante),
        'es_ultima': (idx == total)
    })

def resultado_examen(request):
    sesion_id = request.session.get('kiosk_session_id')
    if not sesion_id:
        return redirect('classroom_exams:acceso')
        
    sesion = get_object_or_404(KioskSession, id=sesion_id)
    return render(request, 'classroom_exams/resultado.html', {'sesion': sesion})

def accion_profesor(request):
    sesion_id = request.session.get('kiosk_session_id')
    sesion = get_object_or_404(KioskSession, id=sesion_id)
    
    if request.method == 'POST':
        pin_ingresado = request.POST.get('pin')
        accion = request.POST.get('accion')
        
        if pin_ingresado == sesion.config.pin_profesor:
            if accion == 'reiniciar':
                request.session.flush()
                return redirect('classroom_exams:acceso')
            elif accion == 'revisar':
                return render(request, 'classroom_exams/hoja_examen.html', {
                    'sesion': sesion,
                    'preguntas': sesion.examen_snapshot,
                    'modo_revision': True
                })
        else:
            messages.error(request, "PIN Incorrecto")
            
    return redirect('classroom_exams:resultado_examen')
