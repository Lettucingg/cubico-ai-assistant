"""Do not turn an unresolved delivery complaint into a guessed logistics state."""
import re
import unicodedata

DELIVERY_RULES = """
ENTREGAS Y RETIROS: Una solicitud de domicilio, una factura pagada o una promesa
anterior no prueban que un paquete salió a reparto. No digas «está en ruta hacia
ti» sin un despacho vigente confirmado. Reparto suspendido tampoco demuestra
que no se pueda retirar. Solo confirma retiro o recogida por PedidosYa si hay
autorización actual del equipo o datos inequívocos; no autorices ni lo niegues
por un campo ausente o un estado crudo. Una autorización explícita del equipo
en el historial es un antecedente relevante: no la contradigas por ausencia de
otro dato; confirma si sigue vigente antes de coordinar. Si el cliente ya dijo
que necesita domicilio, no insistas en que vaya al local. Un reclamo por demora
debe indicar al equipo qué falta comprobar, sin prometer una fecha o devolución
de llamada. Recibir un comprobante no equivale a validar un pago.
"""


def delivery_complaint(text):
    plain = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    return bool(re.search(r'\bno (?:he|hemos|ha|han) recibido (?:el|los|mi|mis) paquetes?\b'
                          r'|\b(?:entrega|domicilio)\b.{0,60}\bpendiente\b.{0,40}\b(?:semana|dias)\b', plain))
