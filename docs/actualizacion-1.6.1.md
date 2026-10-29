# Cúbico 1.6.1 — consultas generales y preparación de campaña

## Listo en esta versión

- Botón «Consultar a Bruno» en la fila de accesos del panel, disponible sin seleccionar un cliente. Abre un lateral con consulta general, borrador y copia manual. El resultado se conserva al cerrar y reabrir; se elimina al cerrar sesión.
- Endpoint autenticado POST `/panel/asistente`, separado del existente `/panel/asistente/{telefono}`. Las consultas generales no leen cuentas privadas por un código escrito en la pregunta. Los saldos y facturas se siguen consultando desde el chat vinculado.
- Hasta tres trackings explícitos usan la consulta pública existente. Las dudas generales usan una sola llamada medida de IA, sin herramientas de escritura ni reintentos automáticos. Los resúmenes operativos consultan conteos locales y muestran fuente no disponible cuando falla.
- Yappy queda deshabilitado por defecto, aunque exista un número antiguo en `.env`. Las respuestas automáticas y las ayudas de redacción reciben la política vigente. Para activarlo después se requieren `CUBICO_YAPPY_ENABLED=true` y un destino de pago confirmado en `CUBICO_PAYMENT_YAPPY`; reiniciar y verificar antes de ofrecerlo.
- Horarios: lunes a viernes 10–17, sábados 10–13, hora de Panamá. Estimados Miami aéreo 2–3 días hábiles desde recepción; marítimo 7–10 desde salida. China aéreo 12–15; marítimo 30–45. Avisos operativos prevalecen.
- Reglas contra afirmar modalidad por un nombre guardado (OCEAN), confundir transporte tienda–bodega con Panamá, inventar impuestos, ubicación o autorización de retiro.

## Campaña: preparación, no lanzamiento

La guía SOMOSCUBICO está incorporada como conocimiento interno, con precio USD 2.10 y condiciones. **No se ha activado la promoción ni iniciado un envío masivo.** El bot no puede verificar invitados ni vencimiento desde la plataforma emisora actual: esas consultas se escalan. No se promete «solo hoy» indefinidamente ni se aplica una tarifa por conocer el código.

Antes de lanzar se debe definir vencimiento por invitación y conectar una fuente de destinatarios elegibles. También integrar la baja persistente con la plataforma emisora, para que futuros envíos excluyan al contacto. Esta versión NO afirma que ya quedó eliminado: registra atención humana mediante la herramienta existente. La supresión de publicidad no debe bloquear atención transaccional solicitada por el cliente.

No se incorporaron como políticas confirmadas el recargo de carga peligrosa, mínimos aéreos, autorización de terceros ni afirmaciones generales de exención tributaria. Requieren confirmación operativa.

## Instalación y comprobación

```bash
cd /home/alexander/cubico-ai-assistant
git pull --ff-only && pm2 restart cubico-bot && pm2 save
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/admin
```

Recargar el panel y comprobar v1.6.1. Probar Consultar a Bruno sin cliente: formas de pago, horario y una pregunta sobre campaña; preparar/copy sin envío. Después comprobar un chat verificado y su consulta de saldo. No se cambian argumentos de PM2, puerto, tablas de negocio ni requisitos.

## Validación

Pruebas automatizadas con proveedor simulado: 20 tipos de consulta general comprueban límites, privacidad, medición y política enviada al modelo. No sustituyen 20 conversaciones reales con Claude o WhatsApp. Se comprueban autenticación, errores, tracking público, respuesta inválida, Yappy inactivo y aislamiento de cuentas. Comprobación en Chromium con anchos 360, 390, 430 y 1440 px: lateral sin desbordamiento, cierre/reapertura, resultado persistente y cierre con viewport reducido. No equivale a prueba en dispositivos iOS/Android reales. Pruebas DOM cubren doble clic, cierre/reapertura, texto seguro, logout y fallos; regresiones de chat/panel y versión.
