# Diagnóstico de entrega de WhatsApp — 1.6.6

El estado `accepted` solo indica que Meta aceptó una petición. El webhook posterior puede indicar `sent`, `delivered`, `read` o `failed`.

Los recibos se guardan en una tabla independiente del historial del chat y del registro de costes. Incluyen el identificador del mensaje, destinatario, estado, timestamp de Meta y hasta diez errores con código, título, mensaje y detalle. No se conserva el webhook completo ni las cabeceras de autenticación. La tabla se crea al cargar el servicio; no modifica las columnas del registro de costes existente.

Tras actualizar y reiniciar el bot, los próximos recibos tendrán este diagnóstico, incluidos los de envíos realizados por terminal. Todos los recibos de un lote se procesan y los duplicados exactos no se vuelven a insertar. Una actualización de coste fallida no impide guardar el diagnóstico. Un recibo fuera de orden o una respuesta HTTP tardía tampoco borran el error anterior.

Consulta de solo lectura desde el proyecto:

```bash
venv/bin/python -m app.services.delivery_diagnostics --telefono NUMERO_INTERNACIONAL
```

Devuelve los envíos recientes y sus recibos. El teléfono se muestra parcialmente oculto; la consulta no envía mensajes, no programa reintentos ni borra bloqueos. El motivo mostrado es el que comunicó Meta; si Meta no envió detalles, la lista de errores estará vacía.

**No recupera errores anteriores a la instalación** si no se guardaron en otra fuente. Para esos envíos informa del estado conocido y de la ausencia de detalle. Instalar esta actualización no vuelve a mandar las pruebas fallidas: cualquier nuevo intento debe decidirse por separado.

Los casos de prueba usan SQLite aislado y recibos simulados, sin llamadas ni mensajes reales a Meta.
