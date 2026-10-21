# Centro de incidencias y Claude personal · v1.5.3

## Publicación

Desde `/home/alexander/cubico-ai-assistant`:

```sh
git pull --ff-only
venv/bin/pip install -r requirements.txt
pm2 restart cubico-bot
```

Desde v1.5.0 se agregaron dos tablas para incidencias y conexiones. v1.5.3 agrega una tercera para autorizaciones OAuth mediante `create_all`; conserva sesiones, perfiles y datos anteriores. Comprueba en Configuración que el servidor muestre v1.5.3 y recarga el panel. No es necesario cambiar variables de proveedores ni reiniciar la web Node de tracking.

## Incidencias y mejoras

El acceso está en Sistema y en Configuración. Desde v1.5.1 el botón abre un panel lateral sin cambiar la pantalla actual. Se puede minimizar o cerrar y reabrir conservando el borrador y la captura durante la sesión; «Descartar borrador» los elimina. Al guardar no cambia el chat ni su texto pendiente. Cerrar sesión elimina el borrador local de la incidencia. El botón «Reportar un problema o idea» registra la sección desde la cual se abrió, versión, navegador, tamaño de pantalla y teléfono del chat activo, si existe. El operador puede revisar y editar ese contexto antes de guardar. Las capturas JPG/PNG de hasta 12 MB se reducen en el navegador a un máximo aproximado de 400 KB antes de subirlas; no se captura la pantalla automáticamente.

Reportes compartidos por el equipo: problema/mejora, sección, título, descripción, comportamiento esperado, prioridad, captura opcional y responsable. Seguimiento: pendiente, en revisión, resuelta o descartada. Se puede reabrir; no hay eliminación irreversible. Cada modificación registra al operador autenticado y evita sobrescribir notas de otra persona con una revisión antigua. El reporte JSON descargable incluye seguimiento y contexto, pero no la captura. Las quejas de la plataforma no se convierten en contexto operativo para Bruno.

La lista muestra hasta 200 resultados por filtro. Los reportes no se envían automáticamente a ChatGPT, GitHub ni a clientes.

## Conexión personal de Claude

Cada persona entra con su propio usuario del panel y abre Configuración → Mi conexión con Claude. Crea una credencial, elige los permisos y copia su valor (solo se muestra una vez). En Claude agrega un conector personalizado:

- URL: `https://bot.cubico.com.pa/mcp/` (con barra final).
- Autenticación: **Sign in now** (Iniciar sesión).
- Registro del cliente: **Register automatically** (Registro automático). No usar Published client identity ni completar Client ID/Secret manualmente.
- Transporte: **Streamable HTTP**.
- Al agregar, Claude abre una página de Cúbico en `https://bot.cubico.com.pa/panel/ia/oauth/consentir`. Pega la clave personal `Bearer cubico_…`, pulsa Revisar permisos, comprueba el usuario y permisos y confirma Autorizar a Claude.
- Activa el conector en la conversación de Claude. Tu hermano hace lo mismo con su usuario y su propia conexión.

No se pide la contraseña de Claude ni una clave API de Anthropic. Si perdiste la clave personal anterior, revoca esa conexión en Cúbico y crea otra. Las credenciales personales anteriores siguen funcionando; el encabezado Bearer directo también se conserva para clientes que admitan configurarlo.

Guía oficial: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp

El proxy debe reenviar `/mcp/`, `/panel/ia/oauth/` y `/.well-known/` a la misma aplicación FastAPI, sin eliminar Authorization. Si solo reenvía algunas rutas, hay que incluirlas. La respuesta 401 de `/mcp/` anuncia la URL de descubrimiento del recurso. El transporte Streamable HTTP y los controladores OAuth usan el SDK oficial MCP 1.30.0, con negociación de versiones compatibles hasta 2025-11-25, respuestas JSON y sin sesiones MCP. No se instala otro servicio.

La autorización usa registro dinámico, código de un solo uso, PKCE S256, protección CSRF, confirmación explícita de permisos y callbacks HTTPS exactos de Claude (`claude.ai` y `claude.com`). Los tokens de acceso duran hasta una hora; su renovación rota y vence con la conexión personal. Revocar la conexión en el panel bloquea tanto la credencial original como sus tokens OAuth. Los códigos y tokens se guardan como hashes. El secreto del cliente OAuth generado por el SDK se cifra con una clave derivada de `CUBICO_NOTIFY_KEY`, que ya existe en el servidor; si se rota esta variable, vuelve a agregar los conectores. Los permisos no se amplían al renovar. Hay límites de solicitudes y tamaño para los endpoints públicos.

Diagnóstico sin credenciales: `curl -i https://bot.cubico.com.pa/mcp/` debe responder 401 y anunciar `resource_metadata`; `curl https://bot.cubico.com.pa/panel/ia/oauth/recurso` y `curl https://bot.cubico.com.pa/.well-known/oauth-authorization-server/panel/ia/oauth` deben devolver metadatos JSON. Una redirección al login del proxy o un 404 indica que faltan rutas. No compartas claves personales en capturas ni chats.

Permisos independientes: conversaciones/tracking público, cuentas verificadas, incidencias/capturas y situación operativa. El permiso de cuentas requiere conversaciones. Hay siete herramientas de consulta; ninguna permite enviar WhatsApp, verificar identidades, cambiar avisos, aprobar pagos, modificar incidencias o ejecutar código. Claude puede redactar con lo consultado y el operador copia el resultado al panel para revisarlo y enviarlo. La conexión no permite usar una suscripción de Claude como clave API dentro de Cúbico.

Ejemplos:

- «Busca el chat del teléfono 507… y lee sus últimos 16 mensajes. ¿Qué necesita el cliente?»
- «Consulta la cuenta verificada de ese chat y prepara una respuesta con el saldo pendiente actual. Distingue las fuentes que no respondieron».
- «Consulta el tracking … y dime si tiene una advertencia de mala identificación».
- «Revisa las incidencias pendientes. Abre INC-0001 y su captura para analizar el problema».

Las consultas solicitadas comparten esos datos con la cuenta de Claude que usa la credencial. No se comparten contraseñas del panel ni claves API del bot. Se almacenan hashes SHA-256 de credenciales aleatorias, permisos, fechas, último uso y última herramienta; no las claves en claro ni argumentos de consultas. Vencen a los 90 días; pueden revocarse desde el usuario que las creó. Máximo 10 conexiones activas por usuario, 60 solicitudes por minuto por credencial. Si un usuario desaparece de PANEL_USUARIOS_JSON, su acceso deja de funcionar. Un cambio de contraseña no revoca estas conexiones independientes: revócalas también si deseas cerrar el acceso de Claude.

No hay llamadas adicionales a OpenAI/Anthropic para estas herramientas: las fuentes se consultan directamente. Las respuestas de Claude consumen los límites que correspondan a su cuenta. La disponibilidad real depende de su plan y del acceso del proxy. Las pruebas locales verifican autenticación, permisos, revocación y transporte; la vinculación con sus cuentas de Claude requiere configurar cada cuenta después del despliegue.
