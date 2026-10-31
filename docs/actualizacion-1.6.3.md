# Cúbico 1.6.3 — comprobantes y destinos de pago

## Problema corregido

Un comprobante mostrado a nombre de otra marca se rechazaba y el bot afirmaba que existía una cuenta propia de Cúbico. El análisis de imágenes recibía el SYSTEM_PROMPT antiguo sin la política dinámica de pagos; su respuesta libre se enviaba directamente al cliente. La configuración conservaba un número antiguo que se ofrecía como transferencia disponible.

## Comportamiento

- Un comprobante recibe siempre: «Gracias, recibí tu comprobante. El equipo revisará el pago y te confirmará su registro».
- El parser y el punto de envío de WhatsApp sustituyen respuestas de la IA que rechacen el destinatario, pidan repetir la transferencia o afirmen que se registró el pago. La extracción de monto, fecha, método y referencia se conserva para la revisión existente.
- El nombre del destinatario, una marca anterior o el uso habitual de una cuenta no demuestran por sí solos que el pago sea correcto o incorrecto. El bot no declara inválido el comprobante ni inventa otra cuenta; el equipo revisa el movimiento.
- Cuando hay un comprobante pendiente y el cliente dice «Siempre hago el pago ahí», la respuesta reconoce ese contexto y pide no repetirlo mientras se revisa.
- Las respuestas generales, la ayuda interna, la redacción y la visión usan la misma política vigente. Yappy sigue desactivado.
- Un número bancario antiguo no se comparte solo porque esté en `.env`. Se requieren CUBICO_BANK_TRANSFER_ENABLED=true, CUBICO_PAYMENT_ACCOUNT y CUBICO_PAYMENT_ACCOUNT_HOLDER confirmados. El titular se muestra tal como se configuró; no se asume que es Cúbico. Con el valor por defecto false no se ofrece cuenta bancaria. No se modifican variables de entorno en el VPS al instalar.

No se registran automáticamente pagos ni se cambian facturas por una imagen. Se conserva el flujo de revisión y registro manual del equipo. No se confirma universalmente que cualquier pago a una marca anterior sea válido.

## Comprobación

Pruebas con salida visual simulada incluyen el rechazo exacto descrito, solicitud de segundo pago y falsa confirmación de saldo cero. La prueba del manejador real de WhatsApp comprueba el acuse enviado, la notificación interna y pago_confirmado=false. No se envían mensajes reales desde desarrollo ni se modifica el caso exportado.

## Instalar

```bash
cd /home/alexander/cubico-ai-assistant
git pull --ff-only && pm2 restart cubico-bot && pm2 save
```

Recargar el panel y comprobar v1.6.3. La política usa configuración segura por defecto; no hay que borrar el número antiguo ni editar archivos para desactivarlo. Cuando exista un destino habilitado, el equipo debe confirmar su titular y activarlo explícitamente.
