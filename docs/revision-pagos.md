# Primera protección de pagos

- Yappy y ACH requieren una referencia legible antes de registrar dinero. Un comprobante recibido sigue pendiente hasta cotejar el ingreso.
- Comparar referencias sin distinguir mayúsculas, espacios exteriores o el prefijo #. Se conserva el texto original en el pago.
- Se bloquea una referencia activa ya registrada para el mismo propietario, incluso cuando se selecciona otra factura o se trata de un abono.
- SQLite reclama la escritura antes de leer pagos y saldos; PostgreSQL conserva el bloqueo del cliente y las facturas.

No cambia saldos históricos, no anula movimientos y no considera duplicados los importes iguales. Un ingreso distribuido entre varias facturas conserva varias aplicaciones legítimas.

## Pendientes de la reestructuración

Esta protección cubre el escritor del bot/panel. El sistema externo debe participar del mismo contrato para impedir duplicados entre ambos escritores. Falta un identificador de operación compartido, recuperación tras un registro financiero exitoso y un fallo posterior al actualizar el comprobante, trazabilidad por operador, revisión de pagos disputados y preferencias de facturación por correo.

Efectivo sigue admitiendo pagos sin referencia. Su protección por identidad de comprobante/operación requiere esa siguiente etapa. No se afirma que el problema completo esté resuelto.

Casos para conciliar en producción: S2N7212, ingreso reportado de 8.10; y la clienta con ingreso reportado de 24.40 del 10 de noviembre por tres paquetes, pendiente de identificar su cuenta y factura. Comparar banco, pagos, aplicaciones y notificaciones antes de corregir. No registrar un segundo ingreso para resolver una mala aplicación.
