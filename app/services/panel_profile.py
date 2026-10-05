"""Preferencias de cuenta y contraseñas persistentes, sin modificar el entorno."""
import base64
import hashlib
import secrets
from app.db.session_store import PerfilPanel, SessionSesiones


def hash_password(password):
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + value


def verify_password(password, encoded):
    salt, expected = encoded.split(":", 1)
    actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return secrets.compare_digest(actual, expected)


def authenticate(usuario, password, defaults):
    if usuario not in defaults:
        return False
    with SessionSesiones() as db:
        row = db.get(PerfilPanel, usuario)
        encoded = row.contrasena_hash if row else None
    if encoded:
        return verify_password(password, encoded)
    return secrets.compare_digest(password.encode("utf-8"), defaults[usuario].encode("utf-8"))


def get_profile(usuario):
    with SessionSesiones() as db:
        row = db.get(PerfilPanel, usuario)
        return {"usuario": usuario, "nombre": row.nombre if row and row.nombre else usuario.capitalize(), "foto": row.foto if row else None}


def validate_photo(foto):
    if foto is None:
        return
    prefixes = {"data:image/jpeg;base64,": b"\xff\xd8\xff", "data:image/png;base64,": b"\x89PNG\r\n\x1a\n"}
    for prefix, signature in prefixes.items():
        if foto.startswith(prefix):
            try:
                data = base64.b64decode(foto[len(prefix):], validate=True)
            except ValueError:
                break
            if len(data) <= 400_000 and data.startswith(signature):
                return
            break
    raise ValueError("Usa una foto JPG o PNG de hasta 400 KB")


def save_profile(usuario, nombre, foto):
    validate_photo(foto)
    with SessionSesiones() as db:
        row = db.get(PerfilPanel, usuario)
        if row is None:
            row = PerfilPanel(usuario=usuario)
            db.add(row)
        row.nombre = nombre.strip()
        row.foto = foto
        db.commit()
    return get_profile(usuario)


def change_password(usuario, password):
    encoded = hash_password(password)
    with SessionSesiones() as db:
        row = db.get(PerfilPanel, usuario)
        if row is None:
            row = PerfilPanel(usuario=usuario)
            db.add(row)
        row.contrasena_hash = encoded
        db.commit()
