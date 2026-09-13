# Panel operativo de Cúbico

El panel ya está conectado al backend de Bruno y se abre en `/admin`. No usa
datos de demostración ni crea un segundo registro de clientes: las colas se
construyen a partir del estado de cada conversación de WhatsApp.

## Qué quedó conectado

- Conversaciones, historial, no leídos y búsqueda.
- Nombre, código CBC, estado y teléfono del cliente.
- Alertas de atención humana.
- Toma de control persistente: mientras está activa Bruno no responde.
- Respuesta directa del operador o respuesta redactada por Bruno.
- Retiros y domicilios solicitados por WhatsApp.
- Pago reportado al detectar un comprobante, visualización del comprobante y
  confirmación manual por el operador.
- Flujo operativo: confirmar pago, preparar paquetes, coordinar domicilio y
  marcar como entregado.
- Tokens de entrada/salida, costo por chat y costo por día.
- Actualización automática cada 30 segundos.

## Variables necesarias

Usa `.env.example` como guía. En el archivo de entorno privado del VPS agrega
las variables existentes y estas tres nuevas:

```env
SESSION_DATABASE_URL=sqlite:///./sesiones.db
ANTHROPIC_INPUT_USD_PER_MTOK=3.0
ANTHROPIC_OUTPUT_USD_PER_MTOK=15.0
```

`SESSION_DATABASE_URL` puede apuntar a PostgreSQL. En el VPS de Hetzner también
se puede dejar sin configurar para continuar usando `sesiones.db`, que permanece
en el disco entre reinicios de PM2. Haz una copia del archivo antes del despliegue.

Los dos precios son configurables: coloca las tarifas de tu modelo/contrato.
El sistema guarda el costo calculado en el momento de cada llamada, por lo que
un cambio futuro de precio no altera el histórico.

Los teléfonos internos, direcciones de bodegas y datos de pago ya no viven en
el repositorio público. Copia sus valores actuales a las variables
`CUBICO_TEAM_COMMAND_NUMBERS_JSON`, `CUBICO_NOTIFICATION_NUMBERS_JSON`,
`CUBICO_PAYMENT_*`, `CUBICO_MIAMI_*`, `CUBICO_CHINA_*` y `CUBICO_LOCAL_*` en el
entorno privado del VPS antes de fusionar o desplegar. Los dos campos `*_JSON` reciben arreglos
como `["50760000000"]`, siempre sin el signo `+`.

## Despliegue

1. Configura las nuevas variables en el archivo de entorno privado que carga PM2.
2. Comprueba y respalda `sesiones.db` si se mantiene SQLite.
3. Fusiona el PR solamente después de la validación y despliega por SSH:

   ```bash
   ssh USUARIO@IP_DEL_VPS
   cd cubico-ai-assistant
   git pull && pm2 restart cubico-bot --update-env
   ```

4. Abre `https://bot.cubico.com.pa/admin` e inicia sesión con una cuenta definida en
   `PANEL_USUARIOS_JSON`.
5. Envía un mensaje de prueba desde un número que no sea el número de Cúbico y
   comprueba que aparece en Conversaciones.

Durante la transición, el panel anterior permanece disponible en
`https://bot.cubico.com.pa/admin-anterior`. Esta ruta permite una reversión operativa
inmediata sin cambiar código ni volver a desplegar.

Las tablas `sesiones` y `uso_ia`, además de las nuevas columnas operativas, se
crean automáticamente al iniciar. Si cambias de SQLite a PostgreSQL, el panel
empieza con las conversaciones nuevas; el archivo SQLite anterior no se migra
automáticamente.

## Comprobantes

Cuando el cliente manda una imagen que Claude reconoce como comprobante:

1. se guarda como pago reportado, todavía no confirmado;
2. se notifica al equipo con el flujo existente;
3. aparece en Retiros y domicilios;
4. el operador puede abrir la imagen y confirmar el pago.

Meta conserva los archivos multimedia por tiempo limitado. Si la descarga ya
expiró, el panel muestra un mensaje para solicitar que el cliente reenvíe la
imagen.

## Nota sobre voz

El bot continúa recibiendo y transcribiendo notas de voz de los clientes. El
botón para que el operador grabe y envíe audio desde el navegador está
desactivado deliberadamente: falta definir una conversión a un formato de audio
aceptado por WhatsApp Cloud API. Los mensajes de texto directos sí están
operativos.

## Verificación realizada

- Compilación de todos los módulos Python.
- Validación sintáctica del JavaScript del panel.
- Arranque de FastAPI y carga de `/admin`.
- Autenticación del panel.
- Lectura de conversaciones y resumen.
- Persistencia de control humano, tokens y costos.
- Flujo de pago reportado y confirmación manual.
