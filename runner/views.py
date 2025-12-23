import random
import json
import base64
import re
import os
import traceback  # <--- NUEVO: Para ver errores reales en logs
from io import BytesIO
from PIL import Image

# Django Imports
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.template.loader import render_to_string

# Librerías Externas
from weasyprint import HTML
import google.generativeai as genai  # <--- Solo Gemini

# Modelos
from exams.models import Exam
from .models import Attempt, AttemptEvent

# --- CONFIGURACIÓN GEMINI ---
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("⚠️ ADVERTENCIA: No se encontró GEMINI_API_KEY en variables de entorno.")

# --- FUNCIONES AUXILIARES ---
def is_staff(user):
    return user.is_staff

def es_docente_o_admin(user):
    return user.is_staff or user.groups.filter(name='Docente').exists()

# ==========================================
# SECCIÓN ALUMNO (LOBBY & EXAMEN)
# ==========================================

# 1. LOBBY
def lobby_view(request, access_code):
    exam = get_object_or_404(Exam, access_code=access_code)
    
    if request.method == "POST":
        nombre = request.POST.get('full_name', '').strip()
        legajo = request.POST.get('student_id', '').strip()
        
        # Verificar si ya completó el examen
        finished_attempt = Attempt.objects.filter(
            exam=exam, student_legajo__iexact=legajo, completed_at__isnull=False
        ).first()

        if finished_attempt:
            return render(request, 'runner/lobby.html', {
                'exam': exam,
                'error': f'Acceso denegado. El alumno con legajo "{legajo}" ya envió este examen.'
            })
            
        # Retomar intento activo
        active_attempt = Attempt.objects.filter(
            exam=exam, student_legajo__iexact=legajo, completed_at__isnull=True
        ).first()

        if active_attempt:
            active_attempt.student_name = nombre
            active_attempt.save()
            return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=active_attempt.id)

        # Crear nuevo intento
        attempt = Attempt.objects.create(
            exam=exam, student_name=nombre, student_legajo=legajo,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return redirect('runner:tech_check', access_code=exam.access_code, attempt_id=attempt.id)
        
    return render(request, 'runner/lobby.html', {'exam': exam})

# 2. TECH CHECK
def tech_check_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/tech_check.html', {'exam': exam, 'attempt': attempt})

# 3. BIOMETRIC GATE
def biometric_gate_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)
    return render(request, 'runner/biometric_gate.html', {'exam': exam, 'attempt': attempt})

# 4. REGISTRO BIOMÉTRICO (Selfie + DNI Urls)
@require_POST
def register_biometrics(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        
        if 'reference_face' in data:
            attempt.reference_face_url = data['reference_face']
        
        if 'dni_image' in data:
            attempt.photo_id_url = data['dni_image']
        elif 'photo_id' in data:
            attempt.photo_id_url = data['photo_id']
            
        attempt.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ---------------------------------------------------------
# 5. VALIDACIÓN DNI CON GEMINI IA (CORREGIDO Y BLINDADO) 🤖
# ---------------------------------------------------------
@require_POST
def validate_dni_ocr(request, attempt_id):
    """
    Versión robusta: Prueba múltiples modelos de Gemini y maneja errores de versión.
    """
    try:
        # 1. Validaciones Iniciales
        attempt = get_object_or_404(Attempt, id=attempt_id)
        
        if not GOOGLE_API_KEY:
            return JsonResponse({'success': False, 'message': 'Error Config: Falta API Key en el servidor.'})

        # 2. Procesar Imagen
        try:
            data = json.loads(request.body)
            image_data = data.get('image')
            if not image_data:
                return JsonResponse({'success': False, 'message': 'No se recibió imagen.'})

            if ';base64,' in image_data:
                _, imgstr = image_data.split(';base64,')
            else:
                imgstr = image_data
            
            image_bytes = base64.b64decode(imgstr)
            pil_image = Image.open(BytesIO(image_bytes))
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error procesando imagen: {str(e)}'})

        # 3. Consultar a Gemini (Estrategia Multi-Modelo)
        print(f"📡 Validando identidad para legajo: {attempt.student_legajo}")
        
        ai_response_text = None
        error_logs = []
        
        # Lista de modelos a probar en orden de preferencia
        modelos_a_probar = [
            'gemini-1.5-flash',          # El ideal (rápido y barato)
            'gemini-1.5-flash-latest',   # Variante frecuente
            'gemini-pro-vision',         # Fallback clásico
            'gemini-1.0-pro-vision-latest' # Fallback legacy
        ]

        for nombre_modelo in modelos_a_probar:
            try:
                print(f"🤖 Probando modelo: {nombre_modelo}...")
                model = genai.GenerativeModel(nombre_modelo)
                
                prompt = """
                Analiza esta imagen de identificación oficial.
                Responde EXCLUSIVAMENTE un JSON con este formato exacto:
                {"es_documento": true, "numeros": "12345678"}
                Si no es legible o no es un documento de identidad, pon "es_documento": false.
                No agregues markdown ni comillas extra, solo el JSON raw.
                """
                
                response = model.generate_content([prompt, pil_image])
                ai_response_text = response.text
                print(f"✅ Éxito con {nombre_modelo}")
                break # ¡Funcionó! Salimos del loop
                
            except Exception as e:
                msg = f"Fallo {nombre_modelo}: {str(e)}"
                print(f"⚠️ {msg}")
                error_logs.append(msg)
                continue # Probamos el siguiente

        # Si todos fallaron
        if not ai_response_text:
            print("❌ Todos los modelos fallaron.")
            return JsonResponse({
                'success': False, 
                'message': f'Error de IA. Detalles técnicos: {"; ".join(error_logs)}'
            })

        # 4. Procesar Respuesta de la IA
        try:
            # Limpieza agresiva por si la IA devuelve ```json ... ```
            clean_text = ai_response_text.replace('```json', '').replace('```', '').strip()
            ai_data = json.loads(clean_text)
        except json.JSONDecodeError:
            print(f"❌ JSON Inválido recibido: {ai_response_text}")
            return JsonResponse({'success': False, 'message': 'La IA no devolvió un formato válido. Reintente.'})

        # 5. Lógica de Negocio
        if not ai_data.get('es_documento'):
             return JsonResponse({'success': False, 'message': 'No se detecta un documento válido. Asegure buena luz.'})

        numbers_found = str(ai_data.get('numeros', ''))
        legajo_alumno = re.sub(r'[^0-9]', '', str(attempt.student_legajo))

        print(f"🔍 Comparando: DNI '{numbers_found}' vs Legajo '{legajo_alumno}'")

        # Validación flexible (match parcial)
        if legajo_alumno and (legajo_alumno in numbers_found or numbers_found in legajo_alumno):
            return JsonResponse({'success': True, 'message': 'Identidad verificada. Ahora enfoca tu rostro.'})
        else:
            return JsonResponse({
                'success': False, 
                'message': f'El documento leído ({numbers_found}) no coincide con el legajo ({legajo_alumno}).'
            })

    except Exception as e:
        # Captura final de cualquier error no previsto
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': f'Error interno del servidor: {str(e)}'}, status=200)

# 6. RUNNER (Examen)
def exam_runner_view(request, access_code, attempt_id):
    exam = get_object_or_404(Exam, access_code=access_code)
    attempt = get_object_or_404(Attempt, id=attempt_id)
    
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    if not attempt.start_time:
        attempt.start_time = timezone.now()
        attempt.save(update_fields=['start_time'])

    items = list(exam.items.all())
    if exam.shuffle_items:
        random.Random(str(attempt.id)).shuffle(items)
        
    total_duration = exam.get_total_duration_seconds()
    elapsed = (timezone.now() - attempt.start_time).total_seconds()
    remaining = max(0, total_duration - elapsed)

    if remaining <= 0:
        return redirect('runner:submit_exam', attempt_id=attempt.id)

    saved_answers = attempt.answers or {}
    initial_step = len(saved_answers)
    
    if initial_step >= len(items):
        initial_step = len(items) - 1

    return render(request, 'runner/exam_runner.html', {
        'exam': exam,
        'attempt': attempt,
        'items': items,
        'total_questions': len(items),
        'remaining_seconds': int(remaining),
        'time_per_item': exam.time_per_item,
        'initial_step': initial_step,
    })

# 7. GUARDAR RESPUESTA
@require_POST
def save_answer(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        current_answers = attempt.answers or {}
        current_answers[str(data.get('question_id'))] = data.get('answer')
        attempt.answers = current_answers
        attempt.save(update_fields=['answers', 'last_heartbeat']) 
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error'}, status=400)

# 8. FINALIZAR
def submit_exam_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.completed_at:
        return redirect('runner:exam_finished', attempt_id=attempt.id)

    exam = attempt.exam
    score = 0
    questions = exam.items.all()
    answers = attempt.answers or {}

    for q in questions:
        selected = answers.get(str(q.id))
        if selected:
            correct = next((o for o in (q.options or []) if o.get('correct')), None)
            if correct and correct.get('text') == selected:
                link = exam.examitemlink_set.filter(item=q).first()
                score += link.points if link else 1.0

    attempt.score = score
    attempt.completed_at = timezone.now()
    attempt.save()
    return redirect('runner:exam_finished', attempt_id=attempt.id)

# 9. PANTALLA FINAL
def exam_finished_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    return render(request, 'runner/finished.html', {'attempt': attempt})

# 10. LOG DE SEGURIDAD
@require_POST
def log_event(request, attempt_id):
    try:
        attempt = get_object_or_404(Attempt, id=attempt_id)
        data = json.loads(request.body)
        event_type = data.get('event_type')
        metadata = data.get('metadata', {})
        valid_types = [t[0] for t in AttemptEvent.EVENT_TYPES]
        if event_type not in valid_types:
            return JsonResponse({'status': 'ignored'}, status=200)
        AttemptEvent.objects.create(attempt=attempt, event_type=event_type, metadata=metadata)
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# 11. DASHBOARD DOCENTE
@login_required
@user_passes_test(is_staff)
def teacher_dashboard_view(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    attempts = Attempt.objects.filter(exam=exam).order_by('-start_time').prefetch_related('events')
    results = []
    for attempt in attempts:
        events = attempt.events.all()
        risk_score = 0
        risk_score += events.filter(event_type='FOCUS_LOST').count() * 1
        risk_score += events.filter(event_type='FULLSCREEN_EXIT').count() * 2
        risk_score += events.filter(event_type='NO_FACE').count() * 3
        risk_score += events.filter(event_type='MULTI_FACE').count() * 5
        risk_score += events.filter(event_type='IDENTITY_MISMATCH').count() * 10
        
        status_color = 'green'
        status_text = 'Confiable'
        show_grade = True 
        if risk_score > 10:
            status_color = 'red'
            status_text = 'Crítico'
            show_grade = False 
        elif risk_score > 4:
            status_color = 'yellow'
            status_text = 'Revisar'
            show_grade = False 
        results.append({
            'attempt': attempt, 'risk_score': risk_score,
            'status_color': status_color, 'status_text': status_text,
            'show_grade': show_grade, 'event_count': events.count()
        })
    return render(request, 'runner/teacher_dashboard.html', {'exam': exam, 'results': results})

# 12. DETALLE INTENTO
@login_required
@user_passes_test(is_staff)
def attempt_detail_view(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    events = attempt.events.all().order_by('timestamp')
    return render(request, 'runner/attempt_detail.html', {'attempt': attempt, 'events': events})

# 13. HOME DOCENTE
@login_required
@user_passes_test(is_staff)
def teacher_home_view(request):
    exams = Exam.objects.all().order_by('-id') 
    return render(request, 'runner/teacher_home.html', {'exams': exams})

# 14. PORTAL
@login_required
@user_passes_test(is_staff)
def portal_docente_view(request):
    return render(request, 'runner/portal_docente.html')

# 15. PDF
@login_required
@user_passes_test(es_docente_o_admin)
def descargar_pdf_examen(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    try:
        cantidad_temas = int(request.GET.get('cantidad', 1))
        cant_faciles = int(request.GET.get('faciles') or 0)
        cant_medias = int(request.GET.get('medias') or 0)
        cant_dificiles = int(request.GET.get('dificiles') or 0)
    except ValueError:
        return HttpResponse("Error: Los valores deben ser números enteros.", status=400)

    cantidad_temas = max(1, min(cantidad_temas, 10))
    pool_faciles = list(exam.items.filter(difficulty=1))
    pool_medias = list(exam.items.filter(difficulty=2))
    pool_dificiles = list(exam.items.filter(difficulty=3))
    
    examenes_generados = []
    for i in range(cantidad_temas):
        tema_label = chr(65 + i)
        seleccion = []
        seleccion += random.sample(pool_faciles, min(len(pool_faciles), cant_faciles))
        seleccion += random.sample(pool_medias, min(len(pool_medias), cant_medias))
        seleccion += random.sample(pool_dificiles, min(len(pool_dificiles), cant_dificiles))
        random.shuffle(seleccion) 
        preguntas_data = []
        claves_tema = []
        for idx, item in enumerate(seleccion, 1):
            opciones = list(item.options or [])
            random.shuffle(opciones)
            letra_correcta = "?"
            for j, op in enumerate(opciones):
                op['letra'] = chr(65 + j)
                if op.get('correct'):
                    letra_correcta = op['letra']
            claves_tema.append(f"{idx}-{letra_correcta}")
            preguntas_data.append({'id': item.id, 'texto': item.stem, 'opciones': opciones})
        examenes_generados.append({'tema': tema_label, 'preguntas': preguntas_data, 'claves': claves_tema})

    html_string = render_to_string('classroom_exams/pdf_variantes.html', {
        'config': {'nombre': exam.title, 'materia': 'Examen Generado'},
        'examenes_generados': examenes_generados,
    })
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()
    filename = f"Examen_{exam.title.replace(' ', '_')}_{cantidad_temas}Temas.pdf"
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
