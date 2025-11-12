import openpyxl
from celery import shared_task
from django.conf import settings
from django.core.files.storage import default_storage # Para leer desde S3/R2
from django.contrib.auth import get_user_model
from tenancy.models import Tenant
from exams.models import Exam, Item, ExamItemLink

User = get_user_model()

# (S1c) Esta es la tarea asíncrona (el "worker") que procesará el Excel
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

            items_creados = []
            
            # 4. Leer el Excel fila por fila (saltando la cabecera 'min_row=2')
            for index, row in enumerate(sheet.iter_rows(min_row=2)):
                # Mapeo de columnas (basado en nuestra plantilla)
                tipo = str(row[0].value).strip() if row[0].value else None
                enunciado = str(row[1].value).strip() if row[1].value else None
                contenido_caso = str(row[2].value).strip() if row[2].value else None
                opcion_1 = str(row[3].value).strip() if row[3].value else None
                opcion_2 = str(row[4].value).strip() if row[4].value else None
                opcion_3 = str(row[5].value).strip() if row[5].value else None
                opcion_4 = str(row[6].value).strip() if row[6].value else None
                respuesta_correcta_num = row[7].value
                dificultad = int(row[8].value) if row[8].value else 1

                # Si no hay enunciado o tipo, saltamos la fila
                if not tipo or not enunciado:
                    continue

                # 5. Lógica de Conversión a JSON (Tu idea de UX)
                options_json = None
                if tipo == 'MC':
                    options_list = []
                    # (Convertimos las columnas planas al JSON que espera la DB)
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
                    points=1 # (Default 1 punto)
                )

        # 8. Limpiar el archivo temporal de S3/R2
        default_storage.delete(temp_file_path)

        # 9. Devolver el ID del examen creado
        return new_exam.id

    except Exception as e:
        # Si algo falla, limpiamos el archivo y lanzamos el error
        if 'temp_file_path' in locals() and default_storage.exists(temp_file_path):
            default_storage.delete(temp_file_path)
        # Celery registrará este error
        raise self.retry(exc=e, countdown=60)
