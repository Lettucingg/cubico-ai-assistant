# Centro de incidencias y Claude personal · v1.5.0

## Publicación

Desde `/home/alexander/cubico-ai-assistant`:

```sh
git pull --ff-only
venv/bin/pip install -r requirements.txt
pm2 restart cubico-bot
```

Esta versión agrega dos tablas en la base de sesiones con `create_all`; conserva sesiones, perfiles y datos anteriores. Comprueba en Configuración que el servidor muestre v1.5.0 y recarga el panel. No es necesario cambiar variables de proveedores ni reiniciar la web Node de tracking.

## Incidencias y mejoras

El acceso está en Sistema y en Configuración. Desde v1.5.1 el botón abre un panel lateral sin cambiar la pantalla actual. Se puede minimizar o cerrar y reabrir conservando el borrador y la captura durante la sesión; «Descartar borrador» los elimina. Al guardar no cambia el chat ni su texto pendiente. Cerrar sesión elimina el borrador local de la incidencia. El botón «Reportar un problema o idea» registra la sección desde la cual se abrió, versión, navegador, tamaño de pantalla y teléfono del chat activo, si existe. El operador puede revisar y editar ese contexto antes de guardar. Las capturas JPG/PNG de hasta 12 MB se reducen en el navegador a un máximo aproximado de 400 KB antes de subirlas; no se captura la pantalla automáticamente.

Reportes compartidos por el equipo: problema/mejora, sección, título, descripción, comportamiento esperado, prioridad, captura opcional y responsable. Seguimiento: pendiente, en revisión, resuelta o descartada. Se puede reabrir; no hay eliminación irreversible. Cada modificación registra al operador autenticado y evita sobrescribir notas de otra persona con una revisión antigua. El reporte JSON descargable incluye seguimiento y contexto, pero no la captura. Las quejas de la plataforma no se convierten en contexto operativo para Bruno.

La lista muestra hasta 200 resultados por filtro. Los reportes no se envían automáticamente a ChatGPT, GitHub ni a clientes.

## Conexión personal de Claude

Cada persona entra con su propio usuario del panel y abre Configuración → Mi conexión con Claude. Crea una credencial, elige los permisos y copia su valor (solo se muestra una vez). En Claude agrega un conector personalizado:

- URL: `https://bot.cubico.com.pa/mcp/` (con barra final).
- Autenticación: sin inicio de sesión / No sign in.
- Encabezado de solicitud: `Authorization`.
- Valor: `Bearer cubico_…` (el valor completo mostrado en el panel).

Guía oficial: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp

La URL debe ser accesible por los servidores de Anthropic; configura el proxy para reenviar `/mcp/` a la misma aplicación FastAPI, sin eliminar el encabezado Authorization. Si el proxy solo reenvía `/panel/`, `/static/` y `/admin`, será necesario añadir esta ruta. No se instala un servidor adicional. El transporte Streamable HTTP usa el SDK oficial MCP 1.30.0, con negociación de versiones compatibles hasta 2025-11-25, respuestas JSON y sin sesiones. El SDK se encarga del protocolo; no se implementa OAuth. Es una credencial fija personal, configurada en los encabezados del conector.

Permisos independientes: conversaciones/tracking público, cuentas verificadas, incidencias/capturas y situación operativa. El permiso de cuentas requiere conversaciones. Hay siete herramientas de consulta; ninguna permite enviar WhatsApp, verificar identidades, cambiar avisos, aprobar pagos, modificar incidencias o ejecutar código. Claude puede redactar con lo consultado y el operador copia el resultado al panel para revisarlo y enviarlo. La conexión no permite usar una suscripción de Claude como clave API dentro de Cúbico.

Ejemplos:

- «Busca el chat del teléfono 507… y lee sus últimos 16 mensajes. ¿Qué necesita el cliente?»
- «Consulta la cuenta verificada de ese chat y prepara una respuesta con el saldo pendiente actual. Distingue las fuentes que no respondieron».
- «Consulta el tracking … y dime si tiene una advertencia de mala identificación».
- «Revisa las incidencias pendientes. Abre INC-0001 y su captura para analizar el problema».

Las consultas solicitadas comparten esos datos con la cuenta de Claude que usa la credencial. No se comparten contraseñas del panel ni claves API del bot. Se almacenan hashes SHA-256 de credenciales aleatorias, permisos, fechas, último uso y última herramienta; no las claves en claro ni argumentos de consultas. Vencen a los 90 días; pueden revocarse desde el usuario que las creó. Máximo 10 conexiones activas por usuario, 60 solicitudes por minuto por credencial. Si un usuario desaparece de PANEL_USUARIOS_JSON, su acceso deja de funcionar. Un cambio de contraseña no revoca estas conexiones independientes: revócalas también si deseas cerrar el acceso de Claude.

No hay llamadas adicionales a OpenAI/Anthropic para estas herramientas: las fuentes se consultan directamente. Las respuestas de Claude consumen los límites que correspondan a su cuenta. La disponibilidad real depende de su plan y del acceso del proxy. Las pruebas locales verifican autenticación, permisos, revocación y transporte; la vinculación con sus cuentas de Claude requiere configurar cada cuenta después del despliegue.
