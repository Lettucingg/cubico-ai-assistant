"""Archivo privado de imágenes de WhatsApp; nunca se publica como recurso estático."""
import hashlib
import os
from pathlib import Path
import tempfile

MAX_IMAGE_BYTES = 20 * 1024 * 1024


def image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise ValueError("El contenido no es una imagen admitida")


def _root(directory=None) -> Path:
    if directory is None:
        from app.core.config import settings
        directory = settings.CUBICO_MEDIA_DIR or (
            Path(__file__).resolve().parents[2] / "data" / "private-images"
        )
    resolved = Path(directory).expanduser().resolve()
    public = Path(__file__).resolve().parents[2] / "app" / "static"
    if resolved == public or public in resolved.parents:
        raise ValueError("El archivo privado no puede estar dentro de app/static")
    return resolved


def _target(media_id: str, directory=None) -> Path:
    if not isinstance(media_id, str) or not media_id or len(media_id) > 256:
        raise ValueError("Identificador de imagen inválido")
    name = hashlib.sha256(media_id.encode("utf-8")).hexdigest() + ".image"
    return _root(directory) / name


def read_image(media_id: str, directory=None) -> bytes | None:
    target = _target(media_id, directory)
    if target.is_symlink():
        raise ValueError("No se permiten enlaces simbólicos en el archivo de imágenes")
    try:
        with target.open("rb") as file:
            data = file.read(MAX_IMAGE_BYTES + 1)
    except FileNotFoundError:
        return None
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen conservada está vacía o excede el límite")
    image_mime(data)
    return data


def save_image(media_id: str, data: bytes, directory=None) -> None:
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen está vacía o excede el límite")
    image_mime(data)
    target = _target(media_id, directory)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    existing = read_image(media_id, directory)
    if existing is not None:
        if existing != data:
            raise ValueError("La imagen conservada no coincide con el mismo identificador")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".incoming-", delete=False) as file:
            temporary = Path(file.name)
            os.chmod(temporary, 0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
        temporary = None
        if hasattr(os, "O_DIRECTORY"):
            descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
