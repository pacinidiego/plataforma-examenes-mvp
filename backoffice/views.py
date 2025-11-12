from django.shortcuts import render
from django.contrib.auth.decorators import login_required

# (Spec S1b: DoD - Docente puede loguearse y acceder a un 'Dashboard')
# @login_required es la magia: protege esta página.
# Si el usuario no está logueado, lo redirige a la página de LOGIN_URL
# (que definiremos en settings.py).
@login_required
def dashboard(request):
    """
    Muestra el Dashboard principal del Docente/Admin.
    Por ahora (S1b) solo muestra la bienvenida.
    """
    
    # Preparamos el contexto para el template
    context = {
        'user': request.user,
    }
    
    # Renderiza el template de HTML
    return render(request, 'backoffice/dashboard.html', context)
