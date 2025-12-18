#!/bin/bash

# DNI a borrar
DNI=${1:-"20635969"}

echo "-----------------------------------------------------"
echo "🗑️  Borrando intentos para Legajo/DNI: $DNI"
echo "-----------------------------------------------------"

python manage.py shell -c "
try:
    from runner.models import Attempt
    
    # CORRECCIÓN: Usamos 'student_legajo' en lugar de 'student_id'
    count_guest, _ = Attempt.objects.filter(student_legajo='$DNI').delete()
    print(f'✅ Invitados (por legajo) borrados: {count_guest}')

    # También intentamos por usuario registrado
    count_user, _ = Attempt.objects.filter(user__username='$DNI').delete()
    print(f'✅ Usuarios registrados borrados: {count_user}')

except Exception as e:
    print(f'❌ ERROR: {e}')
"

echo "-----------------------------------------------------"
echo "🏁 Listo."
echo "-----------------------------------------------------"
