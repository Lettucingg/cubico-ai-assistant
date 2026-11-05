"""Strict boundary to the local Cúbico China-air API; no automatic retries."""
import math
import json
import re
from datetime import date
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.config import settings

def luis_numbers():
    # Internal phones stay in the VPS environment rather than the repository.
    try:
        values = json.loads(settings.CUBICO_CHINA_AIR_LUIS_NUMBERS_JSON)
        if not isinstance(values, list) or not 1 <= len(values) <= 2 or any(
                not isinstance(value, str) or not re.fullmatch(r'507[0-9]{8}', value) for value in values):
            return frozenset()
        return frozenset(values)
    except (ValueError, TypeError):
        return frozenset()


class Package(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    tracking: str = Field(default='', max_length=80)
    cliente: str = Field(default='', max_length=30)
    peso_kg: float | None = Field(default=None, gt=0, le=100000)
    largo_cm: float | None = Field(default=None, gt=0, le=100000)
    ancho_cm: float | None = Field(default=None, gt=0, le=100000)
    alto_cm: float | None = Field(default=None, gt=0, le=100000)
    lb_proveedor: float | None = Field(default=None, gt=0, le=1000000)
    costo_proveedor: float | None = Field(default=None, ge=0, le=10000000)
    contenido: str = Field(default='', max_length=250)
    fecha_recepcion: date | None = None

    @field_validator('tracking')
    @classmethod
    def tracking_format(cls, value):
        value = value.strip()
        if value and not re.fullmatch(r'[A-Za-z0-9-]{5,80}', value):
            raise ValueError('Tracking ilegible o inválido')
        return value

    @field_validator('cliente')
    @classmethod
    def client_format(cls, value):
        value = value.strip().upper()
        if not value:
            return ''
        match = re.fullmatch(r'(?:CBC[ -]*)?(\d{1,8})', value)
        if match:
            return 'CBC-' + match[1].zfill(4)
        if re.fullmatch(r'[A-Z][A-Z0-9_-]{1,19}', value):
            return value
        raise ValueError('Código de cliente inválido')


def validate_packages(values):
    if not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise ValueError('Envía entre uno y diez paquetes por lote')
    packages = [Package.model_validate(value).model_dump(mode='json', exclude_none=True) for value in values]
    trackings = [p['tracking'] for p in packages if p['tracking']]
    if len(trackings) != len(set(trackings)):
        raise ValueError('El aviso contiene el mismo tracking más de una vez; revisarlo antes de registrar')
    return packages


def missing_fields(packages):
    issues = []
    for index, package in enumerate(packages, 1):
        missing = [name for name in ('tracking', 'cliente', 'peso_kg', 'contenido', 'fecha_recepcion') if not package.get(name)]
        dimensions = [package.get(name) for name in ('largo_cm', 'ancho_cm', 'alto_cm')]
        if any(dimensions) and not all(dimensions):
            missing.append('medidas completas')
        if missing:
            issues.append(f"Paquete {index}: falta confirmar {', '.join(missing)}")
    return issues


def local_url(path):
    base = settings.CUBICO_INTERNAL_BASE_URL.rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('La API de Cúbico debe ser http://127.0.0.1:PUERTO')
    return base + '/api/dashboard/china-aereo/' + path


async def post_local(path, body):
    if not settings.CUBICO_CHINA_AIR_ENABLED or not settings.CUBICO_BOT_KEY.strip():
        raise ValueError('China aéreo no está habilitado o falta la clave local')
    url = local_url(path)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
        response = await client.post(url, headers={'x-cubico-key': settings.CUBICO_BOT_KEY}, json=body)
    if not response.is_success:
        # Never echo server bodies, key material or exception headers into WhatsApp.
        raise ValueError(f'Cúbico respondió HTTP {response.status_code}; no se confirmó la operación')
    data = response.json()
    if not isinstance(data, (dict, list)):
        raise ValueError('Respuesta de Cúbico no reconocida')
    return data


def preview_rows(data, count):
    rows = data if isinstance(data, list) else data.get('resultados', data.get('paquetes'))
    if rows is None and count == 1 and isinstance(data, dict) and 'ok' in data:
        rows = [data]
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError('La previsualización no devolvió un resultado por paquete')
    if any(not isinstance(row, dict) or not isinstance(row.get('ok'), bool) for row in rows):
        raise ValueError('La previsualización no tiene el formato esperado')
    return rows


async def preview(packages):
    packages = validate_packages(packages)
    rows = preview_rows(await post_local('previsualizar', {'paquetes': packages}), len(packages))
    # If the server identifies rows, require the same order; never attach a price
    # or customer name to the wrong tracking.
    for package, row in zip(packages, rows):
        server_tracking = (row.get('paquete') or {}).get('tracking')
        if server_tracking and server_tracking != package['tracking']:
            raise ValueError('Cúbico devolvió los trackings en otro orden; revisar el lote')
    return rows


async def register(packages, *, phone):
    if phone not in luis_numbers():
        raise ValueError('Solo Luis puede confirmar un registro de China aéreo')
    packages = validate_packages(packages)
    if missing_fields(packages):
        raise ValueError('Faltan datos confirmados del lote')
    data = await post_local('recepciones', {'paquetes': packages, 'confirmado_por': 'Luis'})
    rows = data.get('resultados') if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) != len(packages) or any(
            not isinstance(row, dict) or not isinstance(row.get('registrado'), bool) for row in rows):
        raise ValueError('El registro no devolvió un resultado confirmado por paquete')
    for package, row in zip(packages, rows):
        if row.get('tracking') and row['tracking'] != package['tracking']:
            raise ValueError('La respuesta de registro no coincide con los trackings enviados')
    return rows


def safe_text(value, limit=350):
    if isinstance(value, list):
        value = '; '.join(str(item) for item in value)
    return re.sub(r'[\x00-\x1f]', ' ', str(value or ''))[:limit]


def summary(packages, rows, warnings=()):
    lines = [f'✈️ {len(packages)} paquetes China aéreo — PREVISUALIZACIÓN, todavía sin registrar.']
    for index, (package, row) in enumerate(zip(packages, rows), 1):
        calculated = row.get('paquete') or {}
        customer = calculated.get('cliente') or {}
        if not isinstance(customer, dict):
            customer = {}
        amount = calculated.get('cobro_estimado')
        pounds = calculated.get('lb_cobrables')
        quote = ''
        if isinstance(amount, (int, float)) and not isinstance(amount, bool) and math.isfinite(amount):
            quote = f' · ${amount:.2f}'
        lines.append(f"{index}. {safe_text(customer.get('codigo') or package['cliente'] or '¿Cliente?', 30)} "
                     f"{safe_text(customer.get('nombre'), 100)} · {safe_text(package['tracking'] or '¿Tracking?', 80)}"
                     f" · {safe_text(pounds or 'sin peso calculado', 40)} lb{quote}")
        lines.append(f"   {safe_text(package.get('contenido'))} · recibido {safe_text(package.get('fecha_recepcion') or 'fecha pendiente', 30)}")
        for label, field in (('ERROR', 'errores'), ('AVISO', 'avisos')):
            if row.get(field):
                lines.append(f'   {label}: {safe_text(row[field])}')
    lines += ['⚠️ ' + safe_text(issue) for issue in [*warnings, *missing_fields(packages)]]
    lines.append('¿Los registro? Responde «sí». Si falta cliente: «sí, 0093». Para corregir uno: «2 CBC-0093». Para cancelar: «cancelar».')
    return '\n'.join(lines)


def main():
    import argparse
    import asyncio
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='China aéreo: configuración y previsualización, sin registrar cargas')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('comprobar')
    commands.add_parser('previsualizar').add_argument('--archivo', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'comprobar':
            result = {'habilitado': settings.CUBICO_CHINA_AIR_ENABLED,
                      'clave_configurada': bool(settings.CUBICO_BOT_KEY.strip()),
                      'numeros_luis_configurados': len(luis_numbers()),
                      'api_local': local_url('previsualizar'), 'conexion_comprobada': False,
                      'nota': 'Solo configuración; no se hicieron llamadas ni registros.'}
        else:
            source = Path(args.archivo)
            if source.stat().st_size > 100000:
                raise ValueError('Archivo demasiado grande')
            values = json.loads(source.read_text(encoding='utf-8'))
            packages = validate_packages(values['paquetes'] if isinstance(values, dict) else values)
            result = {'solo_previsualizacion': True, 'resultados': asyncio.run(preview(packages))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        parser.exit(2, 'No se pudo comprobar la configuración o previsualizar. Revisa clave, habilitación, API local y archivo. No se solicitó ningún registro.\n')


if __name__ == '__main__':
    main()
