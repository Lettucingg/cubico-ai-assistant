# Ficha de domicilio (v1.6.13)

Cada solicitud conserva dirección, barrio, referencias, zona y enlace opcional de Google Maps, Apple Maps o Waze. Una ubicación compartida por el cliente aparece como sugerencia con fecha: el equipo debe comprobar que corresponde a la entrega y elegir usarla.

## Solicitud y programación
Bruno puede capturar el día, fecha y restricción horaria que pide el cliente. Nunca confirma la programación desde esa herramienta. El equipo guarda su fecha e intervalo aparte. Guardar no envía mensajes, no registra pagos y no coordina automáticamente.

Para coordinar se conserva el control de facturación existente y se exige preparación de paquetes, ficha revisada, dirección, zona y fecha vigente de lunes a viernes. El enlace y las horas son opcionales; si se indica un intervalo, deben completarse ambas horas en orden.

- Centro: Condado del Rey, Tumba Muerto, Avenida Balboa, San Francisco, Paitilla, Multiplaza y Soho. Preferencia lunes y miércoles.
- Este: Brisas del Golf, Juan Díaz, Costa del Este, Chanis, Campo Lindbergh, Cerro Viento y San Antonio. Preferencia martes y jueves.
- Las preferencias son orientativas; el equipo puede programar excepciones de lunes a viernes. No se inventa disponibilidad de conductor ni tiempos de viaje.
- Una modificación exige revisar de nuevo la coordinación. Los cambios solicitados por el cliente borran el horario confirmado anterior.
- Los borradores se conservan al alternar solicitudes en la misma página. Si otro operador cambia el caso, se rechaza el guardado obsoleto.

## Persistencia
La tabla nueva `fichas_domicilio` se crea con el mecanismo existente de `BaseSesiones.metadata.create_all`. No modifica columnas de las tablas existentes. Conserva revisiones y quién guardó los datos. Respaldar la base de sesiones antes de actualizar, como en cualquier cambio operativo.

La identidad incluye teléfono, cliente verificado y conjunto de trackings. Los datos de una solicitud anterior no se copian automáticamente a paquetes o clientes distintos. Una dirección modificada por otra vía requiere revisión.

## Prueba operativa
1. Abrir una solicitud real con paquetes identificados y guardar dirección, zona y lo solicitado por el cliente.
2. Comprobar que guardar no registra pagos, no envía mensajes y no marca coordinado.
3. Revisar el mapa opcional y fijar fecha del equipo. Confirmar pago y paquetes preparados antes de coordinar.
4. Cambiar la dirección o la preferencia del cliente: verificar que la coordinación debe revisarse de nuevo.
5. Abrir otra solicitud y comprobar que no hereda los datos del caso anterior.

Esta entrega prepara la información para Mi ruta. No calcula rutas, no registra cobros en efectivo, no marca salidas del sistema Cúbico y no incorpora evidencia fotográfica de entrega.
