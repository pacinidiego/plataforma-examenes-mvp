import openpyxl
from celery import shared_task
from django.conf import settings
from django.core.files.storage import default_storage # Para leer desde S3/R2
from django.contrib.auth import get_user_model
from tenancy.models import Tenant
from exams.models import Exam, Item, ExamItemLink

User = get_user_model()

# --- !! CORRECCIÓN (BUG 2: Bucle Infinito) !! ---
# 1. Definimos las cabeceras esperadas
EXPECTED_HEADERS = [
    "tipo", "enunciado", "contenido_caso", 
    "opcion_1", "opcion_2", "opcion_3", "opcion_4", 
    "respuesta_correcta", "dificultad"
]

# 2. Eliminamos los reintentos automáticos. Si falla, falla.
@shared_task(bind=True)
def process_exam_excel(self, tenant_id, user_id, exam_title, temp_file_path):
    """
    Lee un archivo Excel desde S3/R2 (subido por el docente),
    lo parsea, y crea el Examen y todos sus Ítems.
    """
    try:
        # 1. Obtener los objetos principales
        tenant = Tenant.objects.get(id=tenant_id)
        author = User.objects.get(id=user_id)

        # 2. Crear el Examen (con Shuffle por defecto, como definimos)
        new_exam = Exam.objects.create(
            tenant=tenant,
            author=author,
            title=exam_title,
            shuffle_items=True,
            shuffle_options=True
        )

        # 3. Abrir el archivo Excel desde S3/R2
        with default_storage.open(temp_file_path, 'rb') as f:
            workbook = openpyxl.load_workbook(f)
            sheet = workbook.active

            # --- !! CORRECCIÓN (BUG 2: Validar Cabeceras) !! ---
            headers_in_file = [cell.value for cell in sheet[1]]
            if headers_in_file != EXPECTED_HEADERS:
                # Si las cabeceras no coinciden, es un formato incorrecto.
                # Lanzamos un ValueError, que será reportado al usuario.
                raise ValueError(f"Formato de Excel incorrecto. Cabeceras esperadas: {EXPECTED_HEADERS}, pero se encontró: {headers_in_file}")
            # --- !! FIN CORRECCIÓN !! ---

            items_creados = []
            
            # 4. Leer el Excel fila por fila (saltando la cabecera 'min_row=2')
            for index, row in enumerate(sheet.iter_rows(min_row=2)):
                # Mapeo de columnas
                tipo = str(row[0].value).strip() if row[0].value else None
                enunciado = str(row[1].value).strip() if row[1].value else None
                contenido_caso = str(row[2].value).strip() if row[2].value else None
                opcion_1 = str(row[3].value).strip() if row[3].value else None
                opcion_2 = str(row[4].value).strip() if row[4].value else None
                opcion_3 = str(row[5].value).strip() if row[5].value else None
                opcion_4 = str(row[6].value).strip() if row[6].value else None
                
                respuesta_correcta_num = None
                if row[7].value is not None:
                    try:
                        # (Acepta '1' o '1.0')
                        respuesta_correcta_num = int(float(row[7].value))
                    except (ValueError, TypeError):
                        # Ignoramos si no es un número
                        pass 
                
                dificultad = int(row[8].value) if row[8].value else 1

                if not tipo or not enunciado:
                    continue

                # 5. Lógica de Conversión a JSON
                options_json = None
                if tipo == 'MC':
                    options_list = []
                    if opcion_1:
                        options_list.append({"text": opcion_1, "correct": (respuesta_correcta_num == 1)})
                    if opcion_2:
                        options_list.append({"text": opcion_2, "correct": (respuesta_correcta_num == 2)})
                    if opcion_3:
                        options_list.append({"text": opcion_3, "correct": (respuesta_correcta_num == 3)})
                    if opcion_4:
                        options_list.append({"text": opcion_4, "correct": (respuesta_correcta_num == 4)})
                    options_json = options_list

                # 6. Crear el Ítem en la Base de Datos
                new_item = Item.objects.create(
                    tenant=tenant,
                    author=author,
                    item_type=tipo,
                    stem=enunciado,
                    case_content=contenido_caso,
                    options=options_json,
                    difficulty=dificultad
                )
                items_creados.append((new_item, index))

            # 7. Vincular los ítems creados al examen
            for item, order in items_creados:
                ExamItemLink.objects.create(
                    exam=new_exam,
                    item=item,
                    order=order,
                    points=1
                )

        # 8. Limpiar el archivo temporal de S3/R2
        default_storage.delete(temp_file_path)

        # 9. Devolver el ID del examen creado
        return new_exam.id

    except Exception as e:
        # --- !! CORRECCIÓN (BUG 2: Bucle Infinito) !! ---
        # Si algo falla (formato, tipo de dato, etc.), limpiamos el archivo
        # y RE-LANZAMOS el error para que Celery lo marque como 'FAILURE'.
        # Ya no usamos 'self.retry'.
        if 'temp_file_path' in locals() and default_storage.exists(temp_file_path):
            default_storage.delete(temp_file_path)
        raise e
