"""
Envío masivo de mensajes de WhatsApp con PLANTILLAS pre-aprobadas por Meta.

Herramienta INDEPENDIENTE del bot: no se importa desde app/, no toca la base
de datos de sesiones y no escucha webhooks. Solo lee un Excel de contactos y
dispara una plantilla de marketing a cada uno, con pausa entre envíos.

Uso básico:
    python envio_masivo.py contactos.xlsx
    python envio_masivo.py contactos.xlsx --plantilla promo_septiembre
    python envio_masivo.py contactos.xlsx --dry-run     (no envía nada)

El Excel debe tener una fila de encabezados con al menos la columna "telefono".
La columna "nombre" es opcional; si falta o viene vacía se usa SALUDO_GENERICO.
"""

import argparse
import csv
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx

from app.core.config import settings


# ---------------------------------------------------------------------------
# CONFIGURACIÓN — revisar antes de cada campaña
# ---------------------------------------------------------------------------

# TODO: reemplazar por el nombre EXACTO de la plantilla aprobada en
# Meta Business Manager > WhatsApp Manager > Plantillas de mensajes.
# El nombre va en minúsculas y con guiones bajos, ej: "promo_septiembre_2026".
NOMBRE_PLANTILLA = "CAMBIAR_POR_NOMBRE_DE_PLANTILLA"

# Código de idioma con el que se aprobó la plantilla ("es", "es_MX", "en_US"...).
# Si no coincide con el aprobado, Meta rechaza el envío con error 132001.
IDIOMA_PLANTILLA = "es"

# True  -> la plantilla tiene una variable {{1}} en el cuerpo y se le manda el nombre.
# False -> la plantilla es de texto fijo, sin variables.
# Si esto no coincide con la plantilla real, Meta responde error 132000.
PLANTILLA_USA_NOMBRE = True

# Saludo usado cuando el contacto no trae nombre en el Excel.
SALUDO_GENERICO = "Cliente"

# Costo estimado por mensaje en USD (conversación de marketing).
# Solo sirve para el resumen; el cobro real lo define Meta según el país.
COSTO_POR_MENSAJE = 0.0740

# Pausa en segundos entre un envío y el siguiente.
PAUSA_ENTRE_ENVIOS = 1.5

# Espera adicional cuando Meta responde "demasiadas peticiones" (429 / 130429).
PAUSA_POR_RATE_LIMIT = 60

# Prefijo de país que se agrega a números locales de 7 u 8 dígitos.
# Panamá = "507". Dejar en "" para no tocar nunca los números.
CODIGO_PAIS_POR_DEFECTO = "507"

# Versión de la API de Meta (la misma que usa el bot en app/api/whatsapp.py).
VERSION_API = "v21.0"

TIMEOUT_SEGUNDOS = 20.0


# ---------------------------------------------------------------------------
# LOGGING — a consola y a archivo
# ---------------------------------------------------------------------------

MARCA_DE_TIEMPO = datetime.now().strftime("%Y%m%d_%H%M%S")
CARPETA_LOGS = Path("logs_envios")
ARCHIVO_LOG = CARPETA_LOGS / f"envio_{MARCA_DE_TIEMPO}.log"
ARCHIVO_RESULTADOS = CARPETA_LOGS / f"resultados_{MARCA_DE_TIEMPO}.csv"

log = logging.getLogger("envio_masivo")


def _forzar_utf8_en_consola():
    """La consola de Windows suele venir en cp1252 y rompe los acentos."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def configurar_logging():
    """Escribe el mismo detalle en consola y en logs_envios/envio_<fecha>.log."""
    CARPETA_LOGS.mkdir(exist_ok=True)

    _forzar_utf8_en_consola()

    log.setLevel(logging.INFO)
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"
    )

    a_consola = logging.StreamHandler(sys.stdout)
    a_consola.setFormatter(formato)

    a_archivo = logging.FileHandler(ARCHIVO_LOG, encoding="utf-8")
    a_archivo.setFormatter(formato)

    log.addHandler(a_consola)
    log.addHandler(a_archivo)


# ---------------------------------------------------------------------------
# LECTURA DEL EXCEL
# ---------------------------------------------------------------------------

def _normalizar_encabezado(valor) -> str:
    """'Teléfono ' -> 'telefono'. Quita acentos, espacios y mayúsculas."""
    texto = str(valor or "").strip().lower()
    sin_acentos = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sin_acentos if not unicodedata.combining(c))


def normalizar_telefono(valor) -> str:
    """
    Deja el número en el formato que espera Meta: solo dígitos, con código de
    país y sin '+'. Devuelve "" si no queda nada usable.

    Ejemplos: '+507 6983-7308' -> '50769837308' ; '69837308' -> '50769837308'
    """
    if valor is None:
        return ""

    # Excel a veces entrega los números como float (67891234.0).
    if isinstance(valor, float) and valor.is_integer():
        texto = str(int(valor))
    else:
        texto = str(valor)

    solo_digitos = re.sub(r"\D", "", texto)

    # 00507... -> 507...
    if solo_digitos.startswith("00"):
        solo_digitos = solo_digitos[2:]

    if not solo_digitos:
        return ""

    # Número local sin código de país (Panamá: 7 u 8 dígitos).
    if CODIGO_PAIS_POR_DEFECTO and len(solo_digitos) in (7, 8):
        solo_digitos = CODIGO_PAIS_POR_DEFECTO + solo_digitos

    return solo_digitos


def leer_contactos(ruta_excel: Path, nombre_hoja: str = None) -> list:
    """
    Lee el Excel y devuelve [{'telefono': '507...', 'nombre': 'Ana', 'fila': 2}, ...].

    Descarta filas sin teléfono válido y números repetidos (se queda con el
    primero). Los problemas quedan en el log, no detienen la lectura.
    """
    try:
        import openpyxl
    except ImportError:
        raise SystemExit(
            "Falta la librería openpyxl para leer Excel.\n"
            "Instálala con:  pip install openpyxl"
        )

    if not ruta_excel.exists():
        raise SystemExit(f"No existe el archivo: {ruta_excel}")

    libro = openpyxl.load_workbook(ruta_excel, read_only=True, data_only=True)
    hoja = libro[nombre_hoja] if nombre_hoja else libro.active

    filas = hoja.iter_rows(values_only=True)

    try:
        encabezados = [_normalizar_encabezado(c) for c in next(filas)]
    except StopIteration:
        raise SystemExit(f"La hoja '{hoja.title}' está vacía.")

    if "telefono" not in encabezados:
        raise SystemExit(
            f"La hoja '{hoja.title}' no tiene una columna 'telefono'.\n"
            f"Columnas encontradas: {encabezados}"
        )

    col_telefono = encabezados.index("telefono")
    col_nombre = encabezados.index("nombre") if "nombre" in encabezados else None

    contactos = []
    ya_vistos = set()
    descartados = 0
    duplicados = 0

    for numero_fila, fila in enumerate(filas, start=2):
        if fila is None or all(c is None or str(c).strip() == "" for c in fila):
            continue  # fila en blanco

        crudo = fila[col_telefono] if col_telefono < len(fila) else None
        telefono = normalizar_telefono(crudo)

        if not telefono or len(telefono) < 8:
            log.warning(f"Fila {numero_fila}: teléfono inválido ({crudo!r}), se omite.")
            descartados += 1
            continue

        if telefono in ya_vistos:
            log.warning(f"Fila {numero_fila}: {telefono} está repetido, se omite.")
            duplicados += 1
            continue
        ya_vistos.add(telefono)

        nombre = ""
        if col_nombre is not None and col_nombre < len(fila):
            nombre = str(fila[col_nombre] or "").strip()

        contactos.append({
            "telefono": telefono,
            "nombre": nombre or SALUDO_GENERICO,
            "fila": numero_fila,
        })

    libro.close()

    log.info(
        f"Excel leído: {len(contactos)} contactos válidos "
        f"({descartados} inválidos, {duplicados} duplicados)."
    )
    return contactos


# ---------------------------------------------------------------------------
# ENVÍO A LA API DE META
# ---------------------------------------------------------------------------

def construir_payload(telefono: str, nombre: str, plantilla: str, idioma: str) -> dict:
    """Arma el cuerpo JSON de un mensaje tipo 'template'."""
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "template",
        "template": {
            "name": plantilla,
            "language": {"code": idioma},
        },
    }

    if PLANTILLA_USA_NOMBRE:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": nombre}],
            }
        ]

    return payload


def enviar_plantilla(cliente, url: str, telefono: str, nombre: str,
                     plantilla: str, idioma: str):
    """
    Envía una plantilla a un número.

    Devuelve (exito, detalle). En 'detalle' va el message_id si salió bien,
    o la razón del fallo si no. Reintenta una vez ante errores de red.
    """
    payload = construir_payload(telefono, nombre, plantilla, idioma)

    for intento in (1, 2):
        try:
            respuesta = cliente.post(url, json=payload)
        except httpx.RequestError as e:
            if intento == 1:
                log.warning(f"{telefono}: error de red ({e}). Reintentando...")
                time.sleep(3)
                continue
            return False, f"error de red: {e}"

        if respuesta.status_code == 200:
            try:
                message_id = respuesta.json()["messages"][0]["id"]
            except (KeyError, IndexError, ValueError):
                message_id = "sin id"
            return True, message_id

        # Meta devuelve el detalle del error dentro de 'error'.
        codigo = None
        try:
            error = respuesta.json().get("error", {})
            codigo = error.get("code")
            mensaje = error.get("message", respuesta.text)
            detalle = error.get("error_data", {}).get("details", "")
            razon = f"HTTP {respuesta.status_code} | código {codigo}: {mensaje}"
            if detalle:
                razon += f" ({detalle})"
        except ValueError:
            razon = f"HTTP {respuesta.status_code}: {respuesta.text[:200]}"

        # Rate limit: esperar y reintentar una sola vez.
        if (respuesta.status_code == 429 or codigo in (4, 80007, 130429)) and intento == 1:
            log.warning(
                f"{telefono}: límite de velocidad de Meta. "
                f"Esperando {PAUSA_POR_RATE_LIMIT}s antes de reintentar..."
            )
            time.sleep(PAUSA_POR_RATE_LIMIT)
            continue

        return False, razon

    return False, "falló tras reintentar"


# ---------------------------------------------------------------------------
# CONFIRMACIÓN Y RESUMEN
# ---------------------------------------------------------------------------

def pedir_confirmacion(total: int, costo_estimado: float, plantilla: str,
                       idioma: str, ruta_excel: Path, pausa: float) -> bool:
    """Pide un 'si' explícito en la terminal antes de gastar dinero real."""
    minutos = (total * pausa) / 60

    print("")
    print("=" * 62)
    print("  CONFIRMACIÓN DE ENVÍO MASIVO")
    print("=" * 62)
    print(f"  Archivo           : {ruta_excel}")
    print(f"  Plantilla         : {plantilla}  (idioma: {idioma})")
    print(f"  Número emisor     : {settings.WHATSAPP_PHONE_NUMBER_ID}")
    print(f"  Contactos         : {total}")
    print(f"  Costo estimado    : ${costo_estimado:,.2f} USD "
          f"(${COSTO_POR_MENSAJE:.4f} c/u)")
    print(f"  Pausa entre envíos: {pausa}s (~{minutos:.1f} min en total)")
    print("=" * 62)
    print("")

    pregunta = (f"Vas a enviar a {total} contactos, esto costará aproximadamente "
                f"${costo_estimado:,.2f} USD. ¿Confirmas? (si/no): ")

    try:
        respuesta = input(pregunta).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("")
        return False

    return respuesta in ("si", "sí", "s")


def guardar_resultados_csv(resultados: list):
    """Deja un CSV con el estado de cada número, útil para reintentar fallidos."""
    with open(ARCHIVO_RESULTADOS, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(
            f, fieldnames=["fila", "telefono", "nombre", "estado", "detalle"]
        )
        escritor.writeheader()
        escritor.writerows(resultados)


def imprimir_resumen(resultados: list, total_planeado: int, es_prueba: bool):
    """Resumen final: enviados, fallidos y costo estimado."""
    enviados = [r for r in resultados if r["estado"] == "enviado"]
    fallidos = [r for r in resultados if r["estado"] == "fallido"]
    costo_real = len(enviados) * COSTO_POR_MENSAJE

    titulo = "  RESUMEN DEL ENVÍO"
    if es_prueba:
        titulo += "  (SIMULACIÓN, no se envió nada)"

    print("")
    print("=" * 62)
    print(titulo)
    print("=" * 62)
    print(f"  Contactos procesados : {len(resultados)} de {total_planeado}")
    print(f"  Enviados con éxito   : {len(enviados)}")
    print(f"  Fallidos             : {len(fallidos)}")
    print(f"  Costo total estimado : ${costo_real:,.2f} USD")
    print("=" * 62)

    if fallidos:
        print("")
        print("  Fallidos (primeros 20):")
        for r in fallidos[:20]:
            print(f"    - {r['telefono']} (fila {r['fila']}): {r['detalle']}")
        if len(fallidos) > 20:
            print(f"    ... y {len(fallidos) - 20} más. Ver {ARCHIVO_RESULTADOS}")

    print("")
    print(f"  Log        : {ARCHIVO_LOG}")
    print(f"  Resultados : {ARCHIVO_RESULTADOS}")
    print("")


# ---------------------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------

def parsear_argumentos():
    parser = argparse.ArgumentParser(
        description="Envío masivo de plantillas de WhatsApp desde un Excel."
    )
    parser.add_argument("excel", help="Ruta del archivo .xlsx con los contactos.")
    parser.add_argument("--plantilla", default=NOMBRE_PLANTILLA,
                        help="Nombre de la plantilla aprobada en Meta.")
    parser.add_argument("--idioma", default=IDIOMA_PLANTILLA,
                        help='Código de idioma de la plantilla (ej: "es", "es_MX").')
    parser.add_argument("--hoja", default=None,
                        help="Nombre de la hoja del Excel (por defecto, la primera).")
    parser.add_argument("--pausa", type=float, default=PAUSA_ENTRE_ENVIOS,
                        help="Segundos de pausa entre envíos.")
    parser.add_argument("--limite", type=int, default=None,
                        help="Enviar solo a los primeros N contactos (para pruebas).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simula todo el proceso sin llamar a la API de Meta.")
    return parser.parse_args()


def main():
    args = parsear_argumentos()
    configurar_logging()

    ruta_excel = Path(args.excel)
    plantilla = args.plantilla

    if plantilla == "CAMBIAR_POR_NOMBRE_DE_PLANTILLA":
        raise SystemExit(
            "Todavía no configuraste la plantilla.\n"
            "Edita NOMBRE_PLANTILLA al inicio de envio_masivo.py, o pásala con:\n"
            "    --plantilla nombre_de_la_plantilla"
        )

    log.info(f"Leyendo contactos desde {ruta_excel}...")
    contactos = leer_contactos(ruta_excel, args.hoja)

    if args.limite:
        contactos = contactos[:args.limite]
        log.info(f"Limitado a los primeros {len(contactos)} contactos (--limite).")

    if not contactos:
        raise SystemExit("No hay contactos válidos para enviar.")

    total = len(contactos)
    costo_estimado = total * COSTO_POR_MENSAJE

    if not pedir_confirmacion(total, costo_estimado, plantilla, args.idioma,
                              ruta_excel, args.pausa):
        print("Envío cancelado. No se mandó ningún mensaje.")
        return

    if args.dry_run:
        log.info("MODO SIMULACIÓN (--dry-run): no se llamará a la API de Meta.")

    url = (f"https://graph.facebook.com/{VERSION_API}/"
           f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages")
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    resultados = []
    log.info(f"Iniciando envío de la plantilla '{plantilla}' a {total} contactos.")

    try:
        with httpx.Client(timeout=TIMEOUT_SEGUNDOS, headers=headers) as cliente:
            for indice, contacto in enumerate(contactos, start=1):
                telefono = contacto["telefono"]
                nombre = contacto["nombre"]
                prefijo = f"[{indice}/{total}]"

                if args.dry_run:
                    exito, detalle = True, "simulado"
                else:
                    exito, detalle = enviar_plantilla(
                        cliente, url, telefono, nombre, plantilla, args.idioma
                    )

                if exito:
                    log.info(f"{prefijo} OK     {telefono} ({nombre}) -> {detalle}")
                else:
                    log.error(f"{prefijo} FALLO  {telefono} ({nombre}) -> {detalle}")

                resultados.append({
                    "fila": contacto["fila"],
                    "telefono": telefono,
                    "nombre": nombre,
                    "estado": "enviado" if exito else "fallido",
                    "detalle": detalle,
                })

                # No hace falta esperar después del último.
                if indice < total:
                    time.sleep(args.pausa)

    except KeyboardInterrupt:
        log.warning("Envío interrumpido por el usuario (Ctrl+C).")

    guardar_resultados_csv(resultados)
    imprimir_resumen(resultados, total, args.dry_run)


if __name__ == "__main__":
    main()
