# Cúbico 1.6.2 — el asistente interno encuentra clientes

La consulta «sabes cual es la ubicacion me refiero a la del casillero de alexander santamaria» antes producía una explicación de por qué no podía resolverla. Ahora extrae la referencia explícita, consulta personas/agencias activas, y cuando hay una sola coincidencia construye la dirección con el nombre/código real y la configuración de bodega. Si hay varias, presenta botones y retoma la misma pregunta con la selección. No usa el nombre del operador como identidad del cliente.

El lateral incorpora un buscador por nombre, código o teléfono. También se puede seleccionar un cliente y preguntar saldo o paquetes sin abrir el chat. La consulta usa las mismas fuentes vigentes del asistente existente y no verifica al cliente por WhatsApp ni modifica su conversación. La búsqueda no devuelve correo, cédula, contraseña o dirección residencial; el teléfono mostrado se limita a sus últimos cuatro dígitos.

El casillero usa las plantillas ya existentes del bot (Miami aéreo: CUBICO código UNIT2; marítimo: CUBICO OCEAN código UNIT2). Si no se especifica modalidad, se muestran ambas separadas. Si faltan calle, ciudad/ZIP, teléfono o configuración de China, no se inventan ni se reemplazan por el local de Panamá. La dirección refleja la configuración del servidor; requiere mantenerla correcta.

Las consultas de casillero no requieren una llamada a IA. Las demás consultas conservan la medición de costos. Las coincidencias ambiguas no se eligen automáticamente. Una cuenta inactiva o que cambió debe buscarse de nuevo. Una referencia explícita a otro cliente no reutiliza silenciosamente la selección anterior.

## Pruebas y límites

Se añadió regresión con la pregunta exacta de la captura y 20 variantes, usando consultas SQL reales sobre una base de prueba y configuración de bodega de prueba, sin simular una respuesta de IA. No es una consulta a los datos reales de Alexander. Se prueban nombres con y sin tilde, Santa María/Santamaría, códigos, homónimos, cambio de cliente, errores, permisos, configuración incompleta y ausencia de escrituras. El navegador prueba búsqueda, selección y continuación.

Las pruebas de 20 temas generales de v1.6.1 fueron con proveedor simulado. No se realizaron 20 conversaciones reales de campaña con el bot de producción. El envío masivo sigue pendiente de vigencia, destinatarios elegibles y bajas conectadas al emisor. Esta versión no activa promociones ni envía mensajes.

## Instalar

```bash
cd /home/alexander/cubico-ai-assistant
git pull --ff-only && pm2 restart cubico-bot && pm2 save
```

Recargar el panel, comprobar v1.6.2 y repetir la pregunta de la captura. Si la búsqueda no devuelve al cliente, precisar el nombre o usar su código en el mismo lateral. No existe acceso al VPS desde el entorno de desarrollo para comprobar sus datos en vivo.
