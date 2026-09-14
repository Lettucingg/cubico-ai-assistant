"""Genera una clave VAPID privada en disco y muestra su clave pública."""

import argparse
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--salida", default="vapid_private.pem")
    args = parser.parse_args()
    salida = Path(args.salida)
    if salida.exists():
        raise SystemExit(f"La clave ya existe: {salida}. No se sobrescribió.")

    privada = ec.generate_private_key(ec.SECP256R1())
    salida.write_bytes(
        privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    salida.chmod(0o600)
    publica = privada.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    publica_b64 = base64.urlsafe_b64encode(publica).rstrip(b"=").decode()
    print(f"PUSH_VAPID_PRIVATE_KEY_PATH={salida}")
    print(f"PUSH_VAPID_PUBLIC_KEY={publica_b64}")


if __name__ == "__main__":
    main()
