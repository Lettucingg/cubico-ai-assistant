# Piloto de promoción por WhatsApp

Preparar no envía mensajes. El lote se guarda **pausado**, con un máximo de diez destinatarios. La promoción es `cubico_tarifa_preferencial_210`, idioma `es_PA`, encabezado con logo y botón de registro heredado de la plantilla aprobada. No se usa la plantilla de migración pendiente.

## Dejar preparado hoy

Actualizar el código y reiniciar antes de preparar. No necesita dependencias nuevas:

```bash
cd /home/alexander/cubico-ai-assistant
git pull --ff-only && pm2 restart cubico-bot && pm2 save
venv/bin/python -m app.services.campaign_pilot preparar --id piloto-wa-01 --cantidad 10 --confirmo-permiso-whatsapp
```

La confirmación corresponde al permiso de los destinatarios para recibir mensajes por WhatsApp. Estar en un CSV no demuestra ese permiso. El comando lee `prospectos_campana` con el acceso de lectura existente; no modifica esa tabla ni requiere permisos de escritura en la base comercial. Si aún no está cargada, usar el archivo privado ya revisado:

```bash
venv/bin/python -m app.services.campaign_pilot preparar --id piloto-wa-01 --cantidad 10 --confirmo-permiso-whatsapp --csv /ruta/privada/prospectos_campana.csv
```

No subir el CSV ni datos de destinatarios al repositorio. Debe devolver `estado: pausada`, diez pendientes y una vista previa. Sin esa salida no se debe dar por preparado el servidor. Volver a preparar con el mismo identificador solo consulta el lote existente; no lo amplía ni reemplaza. Los destinatarios quedan reservados para esta campaña incluso si el lote se pausa o vence.

Se excluyen campañas de correo, S2N_REDIRECCION (también cuando el teléfono figura en WhatsApp), notas SACADO/BAJA/NO_CONTACTAR, teléfonos inválidos, duplicados, reservas anteriores y sesiones con atención del equipo pendiente o activa. Se normalizan números nacionales de Panamá. Faltas de nombre usan «cliente». Se comprueban formato y aprobación en Meta y presencia del logo.

## Mañana: activar y comprobar

```bash
venv/bin/python -m app.services.campaign_pilot activar --id piloto-wa-01 --ahora
```

Alternativa, activarlo hoy para una hora explícita de Panamá (sustituir la fecha):

```bash
venv/bin/python -m app.services.campaign_pilot activar --id piloto-wa-01 --cuando 2026-11-05T09:00:00-05:00
```

Solo activar una vez revisado el lote. El scheduler envía un destinatario por minuto. Un bloqueo persistente por minuto limita trabajadores superpuestos del mismo lote. La ventana dura una hora: un servidor que vuelve después no envía el atraso. PM2 debe estar online y con arranque automático; no se cambia la configuración de PM2 desde este módulo.

```bash
venv/bin/python -m app.services.campaign_pilot resumen --id piloto-wa-01
venv/bin/python -m app.services.campaign_pilot pausar --id piloto-wa-01
```

`accepted` significa aceptación de la solicitud, `sent` envío, `delivered` entrega, `read` lectura y `failed` fallo. Se muestran recibos y códigos de Meta, con teléfonos enmascarados. `procesada` indica que se agotó la cola de intentos; no que todos se entregaron. Los recibos pueden llegar después y el resumen continúa leyéndolos. Los códigos 130472 y 131049 del experimento/límite de marketing no se evaden con otro tipo de plantilla ni reintentos automáticos.

Si cambia la plantilla o no se puede comprobar Meta, se pausa. Un resultado incierto pausa el lote. Tres fallos de entrega también lo pausan. Después de una caída, los intentos reclamados pasan a inciertos tras cinco minutos y nunca vuelven a pendientes. No hay garantía de entrega exactamente una vez: se elige no repetir un resultado desconocido y revisarlo manualmente.

Cada envío usa la misma reserva persistente del panel, guarda texto expandido, enlace, autor e identificador de Meta en el historial. Bruno puede explicar la invitación sin un saludo genérico ni pedir identidad para información pública; la invitación no verifica una cuenta ni asigna una tarifa.

Las solicitudes explícitas BAJA/STOP o dejar de recibir mensajes guardan una supresión persistente, avisan al equipo y bloquean promociones del piloto y de «Nuevo chat». Se revisan otra vez antes del intento. Una solicitud concurrente con una petición HTTP ya iniciada no puede retirar ese mensaje. La baja no borra una cuenta, no bloquea atención de servicio y no altera sistemas externos de correo. El scheduler anterior de pruebas del equipo sigue siendo independiente; no utilizarlo para campañas.

## Verificación de desarrollo

Pruebas sin envíos reales: preparación pausada, límite, exclusiones, idempotencia, tiempo futuro y vencimiento, bloqueo por minuto, cambios de plantilla, pausa concurrente, bajas, caídas/timeout sin reintentos, tres fallos, recibos de Meta y conservación de contexto por el emisor del panel. El archivo privado no forma parte del cambio publicado. La preparación y activación en producción necesitan la salida de los comandos anteriores.
