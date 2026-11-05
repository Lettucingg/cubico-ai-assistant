# Registro de China aéreo desde los avisos de Luis

La integración está apagada por defecto. Solo puede usar los números de Luis autorizados en el `.env` del VPS. No utiliza la lista general de comandos como permiso de registro. Ningún modelo puede elegir un destinatario ni ejecutar el registro: extrae JSON, Cúbico calcula los cobros y el código exige confirmación de Luis.

## Instalación y activación

1. Actualizar `main` en `/home/alexander/cubico-ai-assistant`.
2. El administrador instala `CUBICO_BOT_KEY` directamente en el `.env` del bot. No imprimirla, pegarla en WhatsApp ni buscarla desde el bot. La clave es la misma que la API local de Cúbico.
3. Configurar `CUBICO_CHINA_AIR_LUIS_NUMBERS_JSON` como una lista JSON de cadenas, con los dos números completos indicados en las instrucciones privadas de Luis (507 y ocho dígitos, sin espacios). El valor predeterminado `[]` no autoriza a nadie. No guardar teléfonos reales en este repositorio.
4. Establecer `CUBICO_CHINA_AIR_ENABLED=true`. `CUBICO_INTERNAL_BASE_URL` vale por defecto `http://127.0.0.1:3000`; cambiar solo el puerto si Cúbico usa otro. Solo se admite HTTP en 127.0.0.1 con puerto explícito, sin credenciales, rutas, consultas o fragmentos. No usar el dominio público.
5. Reiniciar y guardar PM2:

```bash
pm2 restart cubico-bot --update-env && pm2 save
venv/bin/python -m app.services.china_air_client comprobar
```

Debe mostrar habilitado, clave configurada y dos números autorizados. Este comando solo revisa configuración, no comprueba la conexión ni registra paquetes. No hay nuevas dependencias. El scheduler nuevo usa la base persistente de sesiones para la bandeja y los lotes, no escribe directamente en tablas comerciales. No altera la campaña de WhatsApp ni activa el seguimiento de 45/60 días.

## Uso por Luis

- Reenviar todas las fotos y textos de Lynn desde uno de los dos números autorizados. Se agrupan durante 120 segundos desde el último mensaje. Si Meta entrega varias fotos en el mismo callback, se conserva cada mensaje, en orden y con su ID original.
- Se admiten hasta diez paquetes, treinta fotos, sesenta mensajes, 24.000 caracteres de texto y 20 MB de imágenes por lote (hasta 5 MB cada una). No se omiten fotos al exceder límites: pide dividir el lote. Las imágenes se descargan para una sola llamada multimodal; el uso se registra como `china_aereo_lectura_lote` en los gastos de IA.
- Bruno anuncia que está reuniendo el aviso, extrae datos de todas las fotos y consulta `POST /api/dashboard/china-aereo/previsualizar`. Muestra cliente, tracking, fecha, contenido, libras/cobro calculados por Cúbico, errores y avisos.
- Código cortado: queda sin cliente. Una coincidencia de remitente o contenido solo puede ser una observación; no asigna el código. La fecha no se sustituye por la fecha del reenvío; el contenido no se sustituye por la etiqueta genérica china.
- «sí» confirma un resumen ya presentado. «sí, 0093» completa únicamente clientes pendientes y vuelve a previsualizar antes de registrar. «2 CBC-0093; 3 CBC-0079» corrige paquetes concretos y muestra otra previsualización, sin registrar hasta un «sí» posterior. Se admiten códigos de agencia.
- Datos obligatorios incompletos, errores del servidor o cambio de cobro/tarifa después de una confirmación sin correcciones impiden registrar y requieren revisar el nuevo resumen. Nuevas fotos invalidan la previsualización previa. Un «sí» que llegó antes de terminar el resumen no autoriza el lote.
- Solo después de la confirmación se llama una vez a `POST /api/dashboard/china-aereo/recepciones` con `confirmado_por: Luis`. Cúbico controla duplicados de tracking y envía el correo agrupado por cliente. El bot no envía mensajes a Lynn ni al cliente.
- Bruno informa cuántos paquetes se registraron, errores individuales y si Cúbico confirmó el correo. Solo si todos se registraron prepara el texto para que Luis lo envíe a Lynn; nunca lo envía por su cuenta.

Comandos internos:

- `/china estado`: ver el estado del lote y la última previsualización disponible. Tras finalizar, muestra el estado del último lote sin abrir otro.
- `cancelar`, `no` o `/china cancelar`: cerrar un lote que aún no se está registrando.
- `/china revisado`: después de un resultado incierto y de revisar manualmente Cúbico, Luis libera el flujo para un lote nuevo. No repite el registro ni modifica paquetes.

## Fallos y reinicios

La bandeja se guarda antes del HTTP 200 del webhook. Mensajes repetidos conservan un único ID. Los estados y versiones del lote se reclaman con operaciones condicionales; un índice único permite solo un lote abierto por número. Los números no autorizados siguen el flujo habitual del bot.

No se reintenta automáticamente un registro: una respuesta perdida puede significar que Cúbico guardó paquetes y envió correo. El lote pasa a `uncertain` y queda bloqueado para revisión. Un proceso de confirmación/registro interrumpido pasa a incierto tras diez minutos. La lectura interrumpida pide nuevos datos, sin registrar. Las respuestas parciales se conservan y se reportan; no se confirma a Lynn un lote completo cuando faltan paquetes.

Para apagar el flujo: `CUBICO_CHINA_AIR_ENABLED=false` y reiniciar PM2. Los lotes quedan guardados. Cerrar una ventana de terminal no apaga el scheduler de PM2.

## Validación sin registrar en producción

Se puede guardar un JSON privado con `paquetes` siguiendo el contrato de Cúbico y ejecutar:

```bash
venv/bin/python -m app.services.china_air_client previsualizar --archivo /ruta/privada/prueba-china.json
```

El CLI no tiene comando para registrar. Comprobar con los cinco avisos reales que conserva Luis, sin publicar los trackings ni las fotos. Las tarifas y resultados los devuelve el servidor: el bot no fija USD 12 ni USD 11.50. Las pruebas de desarrollo usan teléfonos y trackings sintéticos, HTTP/Meta/IA simulados y ninguna recepción real.

Queda pendiente la prueba de extremo a extremo en el VPS: configurar clave/números, habilitar y reenviar el primer aviso real de Luis. No afirmar que la conexión o el correo funcionaron hasta observar sus respuestas.
