# Nuevo chat por número — 1.6.7

En Chats, «+ Nuevo chat» permite escribir un teléfono aunque no exista una conversación previa ni una cuenta registrada. Ocho dígitos móviles de Panamá se normalizan al prefijo 507; para otros países se usa el número internacional completo. No se exige código CBC ni correo.

Se consultan las plantillas actualmente aprobadas en la cuenta Meta configurada. Esta versión admite cuerpo de texto con variables numéricas, pie, encabezado de imagen y botones con URL HTTPS fija. Las plantillas rechazadas, pendientes, con documentos, encabezados de texto o botones dinámicos no se ofrecen. La imagen enviada es el logo del proyecto, que aparece en la vista previa. No se permite texto libre como primer contacto fuera de la ventana de atención de WhatsApp.

El operador elige la plantilla, completa sus variables, revisa la vista previa y confirma el permiso de contacto. El botón deshabilita acciones mientras se envía. Una reserva persistente por operador, teléfono y request_id evita repetir el mismo intento al pulsar varias veces o repetir una petición. Un resultado incierto no se reintenta automáticamente. Se respetan los chats que otro operador está atendiendo.

La comprobación previa al envío contrasta aprobación y huella con la vista previa. El envío crea una sesión de conversación, no una cuenta de courier ni una identidad verificada. No asigna tarifas ni modifica pagos o permisos de retiro.

Al aceptar Meta la petición, se conserva en el historial el texto completo con variables sustituidas, nombre e idioma de plantilla, enlace del botón, operador, imagen e identificador de WhatsApp. Bruno recibe ese contenido al procesar una respuesta y debe continuar el tema sin tratar el envío como prueba de identidad o de elegibilidad. Los datos financieros y las condiciones particulares siguen requiriendo sus fuentes verificadas.

Los recibos de entrega actualizan el historial y los diagnósticos existentes. «Aceptado» no significa «entregado». Una restricción de Meta como 130472 puede impedir la entrega a un destinatario; esta función no la elimina ni la evade.

Requiere WHATSAPP_BUSINESS_ACCOUNT_ID y el token con permisos para consultar plantillas, subir medios y enviar mensajes. La lista de números de prueba del programador no aplica a esta función individual del panel: el operador proporciona el destinatario y confirma el permiso. No importa ni programa tandas de clientes.

Pruebas automatizadas con bases aisladas y llamadas de Meta simuladas: no se envían mensajes reales durante la validación.
