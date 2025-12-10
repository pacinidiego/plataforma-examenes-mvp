from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import KioskConfig, KioskSession

def acceso_alumno(request):
    # 1. Buscamos si hay un examen configurado y activo para este Tenant
    # (Por ahora tomamos el primero que esté activo para simplificar)
    config = KioskConfig.objects.filter(activo=True).first()

    if not config:
        return render(request, 'classroom_exams/error_no_examen.html', {
            'mensaje': "No hay ningún examen activo en este momento."
        })

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        dni = request.POST.get('dni')

        if nombre and dni:
            # 2. Creamos la sesión (El "Check-in")
            sesion = KioskSession.objects.create(
                config=config,
                alumno_nombre=nombre,
                alumno_dni=dni
            )
            
            # 3. Guardamos el ID en el navegador para saber quién es
            request.session['kiosk_session_id'] = sesion.id
            
            # 4. Redirigimos al examen (Aún no creamos esta url, pero ya la dejamos lista)
            # return redirect('classroom_exams:rendir_examen') 
            
            # Por ahora, para probar que funciona, mostramos un mensaje simple:
            return render(request, 'classroom_exams/mensaje_temporal.html', {'sesion': sesion})
            
    return render(request, 'classroom_exams/acceso.html', {'examen': config})
