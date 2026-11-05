# Prueba única de WhatsApp — 1.6.5

Esta función programa una plantilla aprobada para un número del equipo. No importa prospectos, no activa una campaña y no crea envíos recurrentes. Cada minuto el proceso existente comprueba si hay pruebas pendientes en la base de datos de sesiones.

## Instalación y preparación

Actualizar el repositorio y reiniciar `cubico-bot`. En el archivo `.env` del servidor, configurar el identificador de la cuenta de WhatsApp Business y los números autorizados para pruebas:

```dotenv
WHATSAPP_BUSINESS_ACCOUNT_ID=IDENTIFICADOR_DE_LA_CUENTA_WHATSAPP
CUBICO_TEST_RECIPIENTS_JSON=["NUMERO_DEL_EQUIPO_CON_CODIGO_DE_PAIS"]
```

El identificador corresponde a la cuenta WhatsApp Business (WABA), no al número de teléfono ni al identificador de plantilla. El token existente debe poder consultar las plantillas de esa cuenta y enviar mensajes. No compartirlo en chats ni añadirlo al repositorio.

Tras guardar la configuración, reiniciar el proceso para que la cargue. La función queda sin destinatarios habilitados por defecto.

## Programar

Desde el proyecto, ejecutar el módulo con la fecha y hora acordadas. El ejemplo siguiente usa datos deliberadamente ficticios que deben sustituirse; no es una prueba ya programada:

```bash
venv/bin/python -m app.services.scheduled_template_test programar \
  --id prueba-cuenta-001 \
  --telefono NUMERO_DEL_EQUIPO_CON_CODIGO_DE_PAIS \
  --plantilla cubico_actualizacion_casillero_v2 \
  --idioma es \
  --cuando 'AAAA-MM-DDT09:00:00-05:00' \
  --valores '["Equipo de prueba","TEST-0000"]'
```

Se consulta Meta y solo se guarda si la plantilla está aprobada, el idioma coincide, las variables numéricas coinciden con los valores y el destinatario pertenece a la lista de pruebas. Se devuelve la vista previa. Repetir el mismo identificador y los mismos datos no duplica la programación. No se puede reutilizar ese identificador para modificar datos o repetir un envío.

La primera versión admite cuerpo de texto y pie, sin encabezados ni botones. Usar solo valores ficticios en pruebas.

## Consultar y cancelar

```bash
venv/bin/python -m app.services.scheduled_template_test listar
venv/bin/python -m app.services.scheduled_template_test cancelar --id prueba-cuenta-001
```

Estados: `programada`, `cancelada`, `en_proceso`, `aceptada`, `bloqueada`, `fallida`, `incierta`, `vencida`. `aceptada` significa que Meta devolvió un identificador; no acredita entrega ni lectura. Los recibos de Meta se siguen registrando en el sistema existente de métricas. Esta primera versión se gestiona por terminal y no incluye notificaciones push de finalización.

Antes del envío se vuelve a comprobar la aprobación y el contenido de la plantilla, su categoría y el destinatario permitido. Si cambian, la prueba queda bloqueada. Una prueba con más de una hora de retraso se omite. La programación persiste después de reiniciar, pero el proceso del bot debe estar activo y conectado a Meta.

No hay reintentos de envío automáticos. Si la conexión se interrumpe durante el envío, Meta podría haberlo recibido: se conserva como incierto para revisión manual. Un reinicio tras reservar la prueba tampoco provoca un segundo envío. No cambiar su estado directamente en la base de datos para intentar repetirla.

## Antes del envío real a clientes

Falta confirmar aprobación de la plantilla, prueba de recepción real, integración de bajas, reglas del bot para las respuestas y selección de destinatarios. Aprobar una prueba no autoriza ni programa el envío masivo.
