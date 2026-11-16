# Conservación privada de fotos y comprobantes

## Alcance
- La descarga común consulta primero la copia en disco y solo usa Meta si falta.
- Las imágenes entrantes se intentan conservar antes del buffer/visión de IA.
- Las imágenes subidas desde el panel también se conservan tras obtener el identificador de Meta.
- Abrir una imagen antigua intenta descargarla y conservarla si aún está disponible en Meta.
- El historial y la identidad del comprobante siguen mandando: tener un archivo en disco no concede acceso desde otro chat.
- Los endpoints conservan autenticación, validan la pertenencia y envían el MIME real, no siempre JPEG.
- No cubre todavía audio, PDF, archivos anteriores ausentes ni recuperar imágenes que Meta ya no entrega.
- No afirma que una imagen expiró ante cualquier error.

## Directorio
Por defecto: `data/private-images` dentro del proyecto, fuera de `app/static`. Para un volumen persistente externo, configurar `CUBICO_MEDIA_DIR=/ruta/privada/absoluta` en el servidor. La configuración no admite el interior de `app/static`.

Las imágenes usan nombres derivados del SHA-256 del identificador de Meta, directorio 0700 y archivos 0600. Se guardan los bytes originales, sin edición ni exposición en URLs estáticas. Escritura temporal y reemplazo atómico con fsync. Límite: 20 MiB por imagen.

No hay borrado automático. Vigilar espacio libre y añadir este directorio al respaldo cifrado/privado habitual. Guardar en disco no equivale a tener una copia de seguridad: sustituir o perder el volumen sin respaldo puede perder imágenes.

Si el disco falla, se registra el error y la recepción continúa; no se afirma que esa imagen quedó archivada. Corregir permisos/espacio antes de considerar resuelto el archivo permanente.

## Comprobación antes de instalar
- Revisar ruta del volumen persistente, permisos y espacio.
- Ejecutar pruebas aisladas en CI, sin claves reales ni llamadas a Meta.
- Conservar SHA anterior al desplegar. No requiere migración ni cambios financieros.
- Enviar una imagen de prueba al bot y comprobar que abre en el panel.
- Volver a abrirla y comprobar que el archivo privado sigue disponible tras reiniciar.
- Confirmar que un usuario sin sesión o un chat distinto no puede descargarla.
- Abrir fotos antiguas disponibles para conservarlas; si no se descargan, revisar el error real antes de pedir reenvío.

## Estado de validación
Esta entrega se preparó mediante el conector del repositorio porque el ejecutor local no está disponible. Incluye pruebas de almacenamiento e integración y una comprobación automatizada de GitHub Actions. No se deben declarar aprobadas hasta observar el resultado de esa ejecución. No se ha instalado en producción.
