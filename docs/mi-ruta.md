# Mi ruta (1.6.14)

Acceso: **Solicitudes → Mi ruta**. Vista personal del conductor para fecha y zona seleccionadas; usa el día de Panamá que devuelve el servidor.

## Antes de salir

1. Revisar solicitudes, pagos, dirección, zona y fecha en la ficha del domicilio. Solo las solicitudes activas, pagadas en facturación, preparadas y coordinadas con ficha vigente entran en la lista de paradas listas. Los datos bancarios y la foto del comprobante no sustituyen la consulta del saldo.
2. Elegir fecha y zona. El orden inicial usa horario explícito, prioridad y zona; las flechas permiten ajustarlo. No usa tráfico, distancias ni asegura la ruta más corta.
3. Cotejar los trackings y marcar que todos los paquetes de cada parada están cargados. Esta lista es personal, se conserva por usuario y día y mantiene sus marcas al filtrar zonas. No asigna exclusividad a un conductor.
4. Abrir modo de recorrido: solo hoy, de lunes a viernes, con todas las paradas visibles listas y verificadas y sin una suspensión general de domicilios en los avisos operativos.

El orden, la dirección, las referencias, los horarios solicitados y confirmados, el teléfono y los trackings quedan juntos. Se abre el enlace que proporcionó el cliente si está guardado; sin él, Maps y Waze ofrecen una búsqueda por dirección. Una búsqueda requiere verificar el destino. El pin sigue siendo opcional. Las coordenadas se pasan a Waze únicamente cuando vienen explícitas en un enlace de Maps, sin geocodificación ni inferencias.

El recorrido se actualiza al abrirlo, al cambiar de parada y al regresar a la pestaña visible. Una caída de red o un conflicto descarta la vista utilizable hasta actualizar. Los cambios de ficha, paquetes o estado del pago invalidan la marca de carga cuando ya no coincide su huella. Nuevos paquetes o casos entregados desaparecen de la selección anterior.

## Lo que significa cada acción

- **Carga verificada:** el usuario cotejó los trackings. Es una lista de comprobación, no el despacho de Cúbico.
- **Abrir mapa / llamar / copiar / siguiente:** navegación; no confirma una entrega ni manda mensajes al cliente.
- **Ver solicitud:** vuelve al caso existente para las acciones autorizadas de pago, preparación, coordinación o entrega.

Usar los controles con el vehículo detenido. El modo de recorrido no incluye edición bancaria ni registro de cobros en efectivo. No se han implementado todavía sincronización de salidas con el sistema Cúbico, asignación exclusiva entre conductores, evidencia de entrega/foto, entrega parcial o conciliación de efectivo.

## Persistencia y puesta en producción

La nueva tabla `planes_ruta_panel` se crea por el mecanismo existente `BaseSesiones.metadata.create_all`. No altera columnas de otras tablas. Guarda orden, carga y revisión por usuario/día, con control de cambios entre pestañas. Respaldar la base de sesiones antes de actualizar. No se toca facturación ni el historial del cliente desde estos endpoints.

Prueba tras instalar: revisar una solicitud pagada con fecha de hoy, abrir Mi ruta, verificar la carga, abrir mapa y recorrer paradas. Volver a Solicitudes y comprobar que ninguna se marcó entregada. Cambiar una referencia o un tracking y comprobar que exige cotejar de nuevo la carga. Con otro usuario, el plan personal debe estar vacío. Confirmar en móvil que los botones son cómodos antes del uso en reparto.
