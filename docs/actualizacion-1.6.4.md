# Cúbico 1.6.4 — avisos, pagos e idioma

## Qué corrige

- Contexto operativo: cada aviso indica «Bruno lo usa ahora» o «Bruno NO lo usa» con su estado. «Servicio suspendido» describe el impacto del aviso, separado de si está activo. La cabecera enumera los avisos que aplican ahora.
- Al activar un borrador con revisión vencida, se puede indicar una nueva revisión en la misma acción. Cancelar lo mantiene inactivo. Se conservan los controles de vigencia, conflictos, versión e historial. Las fechas usan mes escrito y hora de Panamá.
- Pagos: los destinos anteriores configurados y autorizados por el equipo vuelven a estar disponibles. No se presentan como cuentas propias de Cúbico ni como teléfonos para llamadas; el titular personal no se añade espontáneamente. El panel muestra los medios que el bot tiene disponibles.
- Comprobantes: se mantienen pendientes de revisión, sin rechazar por una marca anterior, solicitar otro pago ni confirmar un saldo cero por la imagen.
- Idioma: las respuestas siguen el idioma del cliente, incluyendo inglés. Los mensajes internos, ejemplos en español y avisos operativos no deben cambiarlo. Un «ok», un tracking o un comprobante sin texto conservan el idioma de la conversación. También se aplica a la redacción asistida.

## Configuración y límites

`CUBICO_LEGACY_PAYMENTS_ENABLED=true` permite los destinos anteriores de `CUBICO_PAYMENT_ACCOUNT` y `CUBICO_PAYMENT_YAPPY` que el equipo ya autorizó. Sin datos configurados, el bot pide confirmación al equipo y no inventa números. `false` los deshabilita salvo activación explícita de los medios correspondientes. Las credenciales y destinos reales no forman parte de este cambio.

Un borrador no se activa al guardar; requiere Activar y una revisión futura. Las pruebas automatizadas usan datos ficticios y proveedores simulados: no se enviaron WhatsApp ni se validaron cobros reales. La elección de idioma cubre español/inglés; el contenido generado por IA requiere seguimiento de calidad.

Este cambio no inicia campañas masivas ni carga prospectos. La instalación en producción requiere actualizar el repositorio y reiniciar `cubico-bot`.
