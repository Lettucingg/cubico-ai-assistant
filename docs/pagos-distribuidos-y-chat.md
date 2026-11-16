# Pagos distribuidos y chat móvil — 1.6.11

## Operador

1. Revisar el comprobante, titular autorizado, movimiento real, referencia y fecha.
2. Marcar las facturas a las que corresponde. Ninguna se selecciona automáticamente.
3. Revisar los trackings debajo de cada factura y editar los importes si es un abono.
4. La suma debe coincidir con el importe recibido. Ejemplo: $13.50 = $5.40 + $8.10.
5. Confirmar una sola vez. Las aplicaciones se guardan en una transacción con una referencia común, sin multiplicar el importe recibido.

Un comprobante procesado no se compara otra vez contra una factura nueva. No se reparan pagos anteriores ni se reasignan automáticamente: hay que conciliarlos en facturación. Se incluye la consulta de PR106: `python -m app.services.payment_audit --factura FAC-00278`.

## Registro financiero

No requiere migración: cada fila de `pagos` representa la porción aplicada a su factura. Una distribución comparte referencia; la suma de las filas es el movimiento recibido. Reportes que cuenten movimientos bancarios por filas deben agrupar por cliente/referencia y no interpretar cada aplicación como un nuevo ingreso completo. Los reportes por importe siguen sumando importes asignados.

- Validación de propiedad, saldos y suma con Decimal/centavos.
- Bloqueo del cliente y facturas en PostgreSQL; orden fijo de bloqueo.
- Rechazo de referencia existente sin distinguir mayúsculas y espacios externos.
- Una distribución múltiple requiere referencia legible. No se autoriza automáticamente un destino por la imagen.
- Se valida la identidad del comprobante al confirmar.
- El compromiso financiero y el estado de la sesión están en bases distintas: si se interrumpe el guardado de la sesión después del commit, conciliar por referencia; no repetir ni eliminar el pago.

## Chat móvil

La conversación abierta ocupa el viewport visible. El encabezado y las herramientas se compactan; la navegación global se recupera con Volver. La altura sigue `visualViewport` al abrir teclado, rotar y volver a la app. Consultar a Bruno y corregir texto siguen disponibles; esta entrega no activa aún corrección automática ni revisión automática de contexto.

## Comprobaciones de instalación

- Confirmar v1.6.11 en servidor y recargar el panel.
- Revisar que se ven las casillas e importes por factura antes de confirmar pagos reales.
- En iPhone/Android: abrir chat, escribir texto largo, cerrar teclado, consultar a Bruno, abrir Gestionar, volver a la lista y navegar a otra sección.
- Probar el pago de varias facturas en entorno de pruebas; en producción registrar únicamente pagos reales verificados.
- No se cambia la base de datos de producción desde el desarrollo.

## Verificación realizada

46 pruebas Python de facturación, cola/API y persistencia de entradas aprobadas. Pruebas JS de distribución, panel, reanudación, viewport y versión aprobadas. El navegador Chromium local no pudo iniciarse por restricciones de sockets del entorno: la revisión visual real en móvil queda pendiente. Las dependencias del entorno de pruebas no están fijadas a las versiones exactas de producción.

## Reversión

Conservar el SHA anterior al instalar. Si el panel falla, volver al despliegue anterior y reiniciar con el procedimiento habitual. Las aplicaciones financieras ya confirmadas permanecen registradas; una reversión de código no debe borrarlas ni volver a aplicarlas. Antes de desplegar comprobar el respaldo y acceso a recuperación de las bases de producción.
