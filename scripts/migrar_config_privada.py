"""Migra la configuración privada heredada del código hacia .env.

Debe ejecutarse desde la raíz del repositorio antes de desplegar la versión
que elimina esos valores del código. No imprime valores y nunca reemplaza una
variable que ya tenga contenido.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


SCRIPT_PATH = Path(__file__)
ROOT = Path.cwd() if str(SCRIPT_PATH).startswith("<") else SCRIPT_PATH.resolve().parent.parent
ENV_PATH = ROOT / ".env"
WHATSAPP_PATH = ROOT / "app/api/whatsapp.py"
ORCHESTRATOR_PATH = ROOT / "app/ai/orchestrator.py"


def _leer_variables_env(texto: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or "=" not in limpia:
            continue
        clave, valor = limpia.split("=", 1)
        variables[clave.strip()] = valor.strip()
    return variables


def _buscar_linea(lineas: list[str], texto: str) -> int:
    for indice, linea in enumerate(lineas):
        if linea.strip() == texto:
            return indice
    raise ValueError(f"No se encontró la sección requerida: {texto}")


def _siguiente_no_vacia(lineas: list[str], indice: int) -> tuple[int, str]:
    for posicion in range(indice + 1, len(lineas)):
        valor = lineas[posicion].strip()
        if valor:
            return posicion, valor
    raise ValueError("La sección requerida está incompleta")


def _extraer_lista(codigo: str, nombre: str) -> str:
    coincidencia = re.search(rf"^{nombre}\s*=\s*(\[[^\n]+\])", codigo, re.MULTILINE)
    if not coincidencia:
        raise ValueError(f"No se encontró {nombre}")
    numeros = ast.literal_eval(coincidencia.group(1))
    if not isinstance(numeros, list) or not all(isinstance(n, str) for n in numeros):
        raise ValueError(f"{nombre} no contiene una lista válida")
    return json.dumps(numeros, ensure_ascii=False, separators=(",", ":"))


def _extraer_configuracion() -> dict[str, str]:
    whatsapp = WHATSAPP_PATH.read_text(encoding="utf-8")
    orchestrator = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    lineas = orchestrator.splitlines()

    pago = re.search(r"Número de cuenta:\s*([0-9-]+)", orchestrator)
    yappy = re.search(r"Yappy:\s*\n\s*([0-9-]+)", orchestrator)
    if not pago or not yappy:
        raise ValueError("No se encontraron los datos de pago heredados")

    indice_miami = _buscar_linea(lineas, "Dirección del casillero en Miami:")
    indice_calle, calle_miami = _siguiente_no_vacia(lineas, indice_miami)
    indice_unidad, unidad = _siguiente_no_vacia(lineas, indice_calle)
    if unidad != "CUBICO UNIT2":
        raise ValueError("La estructura de la dirección de Miami cambió")
    indice_ciudad, ciudad_miami = _siguiente_no_vacia(lineas, indice_unidad)
    _, telefono_miami_linea = _siguiente_no_vacia(lineas, indice_ciudad)

    indice_aereo = _buscar_linea(lineas, "China Aéreo:")
    indice_marca_aerea, _ = _siguiente_no_vacia(lineas, indice_aereo)
    indice_dir_aerea, direccion_aerea = _siguiente_no_vacia(lineas, indice_marca_aerea)
    indice_operador, _ = _siguiente_no_vacia(lineas, indice_dir_aerea)
    _, telefono_aereo_linea = _siguiente_no_vacia(lineas, indice_operador)

    indice_ocean = _buscar_linea(lineas, "China Marítimo:")
    indice_marca_ocean, marca_ocean = _siguiente_no_vacia(lineas, indice_ocean)
    ruta = re.search(r"\(([A-Za-z0-9-]+)\)\s*$", marca_ocean)
    if not ruta:
        raise ValueError("No se encontró el código de ruta marítima")
    codigo_ruta = ruta.group(1)
    indice_dir_ocean, direccion_ocean_completa = _siguiente_no_vacia(lineas, indice_marca_ocean)
    sufijo = f" {codigo_ruta} (CUBICO-CBC-XXXX)"
    if not direccion_ocean_completa.endswith(sufijo):
        raise ValueError("La estructura de la dirección marítima cambió")
    direccion_ocean = direccion_ocean_completa[: -len(sufijo)]
    indice_buscar, _ = _siguiente_no_vacia(lineas, indice_dir_ocean)
    _, telefonos_ocean_linea = _siguiente_no_vacia(lineas, indice_buscar)
    telefonos_ocean = telefonos_ocean_linea.removeprefix("Teléfono:").strip().split("/")
    if len(telefonos_ocean) != 2:
        raise ValueError("Los teléfonos marítimos no tienen el formato esperado")

    linea_local = next((linea.strip() for linea in lineas if linea.strip().startswith("Local: ")), None)
    if not linea_local:
        raise ValueError("No se encontró la dirección local")
    indice_local = lineas.index(next(linea for linea in lineas if linea.strip() == linea_local))
    _, telefono_local_linea = _siguiente_no_vacia(lineas, indice_local)

    valores = {
        "CUBICO_TEAM_COMMAND_NUMBERS_JSON": _extraer_lista(whatsapp, "NUMEROS_EQUIPO"),
        "CUBICO_NOTIFICATION_NUMBERS_JSON": _extraer_lista(whatsapp, "NUMEROS_NOTIFICACION"),
        "CUBICO_PAYMENT_ACCOUNT": pago.group(1),
        "CUBICO_PAYMENT_YAPPY": yappy.group(1),
        "CUBICO_MIAMI_STREET": calle_miami,
        "CUBICO_MIAMI_CITY_ZIP": ciudad_miami,
        "CUBICO_MIAMI_PHONE": telefono_miami_linea.removeprefix("Tel:").strip(),
        "CUBICO_CHINA_AIR_ADDRESS": direccion_aerea,
        "CUBICO_CHINA_AIR_PHONE": telefono_aereo_linea.removeprefix("Teléfono:").strip(),
        "CUBICO_CHINA_OCEAN_ADDRESS": direccion_ocean,
        "CUBICO_CHINA_OCEAN_ROUTE_CODE": codigo_ruta,
        "CUBICO_CHINA_OCEAN_PHONE_PRIMARY": telefonos_ocean[0].strip(),
        "CUBICO_CHINA_OCEAN_PHONE_SECONDARY": telefonos_ocean[1].strip(),
        "CUBICO_LOCAL_ADDRESS": linea_local.removeprefix("Local:").strip(),
        "CUBICO_LOCAL_PHONE": telefono_local_linea.removeprefix("Teléfono:").strip(),
    }
    if any(not valor for valor in valores.values()):
        raise ValueError("Una o más variables privadas quedaron vacías")
    return valores


def main() -> None:
    if not ENV_PATH.exists():
        raise SystemExit("ERROR: no existe .env; no se realizó ningún cambio")

    texto_env = ENV_PATH.read_text(encoding="utf-8")
    existentes = _leer_variables_env(texto_env)
    valores = _extraer_configuracion()
    pendientes = {clave: valor for clave, valor in valores.items() if not existentes.get(clave)}

    if not pendientes:
        print("Configuración privada ya preparada; no se realizaron cambios.")
        return

    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    respaldo = ENV_PATH.with_name(f".env.backup-{sello}")
    shutil.copy2(ENV_PATH, respaldo)
    respaldo.chmod(0o600)

    separador = "" if not texto_env or texto_env.endswith("\n") else "\n"
    nuevas_lineas = "\n".join(f"{clave}={valor}" for clave, valor in pendientes.items())
    ENV_PATH.write_text(f"{texto_env}{separador}\n# Configuración privada Cúbico\n{nuevas_lineas}\n", encoding="utf-8")
    ENV_PATH.chmod(0o600)
    print(f"Respaldo creado: {respaldo.name}")
    print("Variables agregadas (valores ocultos):")
    for clave in pendientes:
        print(f"- {clave}")


if __name__ == "__main__":
    main()
