"""Safe handling of uploaded photos: validate by content (not filename or the
client's content-type), enforce limits, and store under server-generated names
so client-supplied names can never reach the filesystem."""
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.errors import bad_input

ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def validate_photos(blobs: list[bytes], max_photos: int, max_bytes: int) -> list[tuple[bytes, str]]:
    """Return [(bytes, extension)] or raise BAD_INPUT."""
    if len(blobs) > max_photos:
        raise bad_input(f"At most {max_photos} photos are allowed.")
    out: list[tuple[bytes, str]] = []
    for data in blobs:
        if not data:
            raise bad_input("An uploaded photo is empty.")
        if len(data) > max_bytes:
            raise bad_input(f"A photo exceeds the {max_bytes // (1024 * 1024)} MB limit.")
        try:
            with Image.open(io.BytesIO(data)) as img:
                fmt = img.format
                img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
            raise bad_input("Unsupported or corrupt photo. Use JPEG, PNG or WebP.")
        if fmt not in ALLOWED_FORMATS:
            raise bad_input("Unsupported photo type. Use JPEG, PNG or WebP.")
        out.append((data, ALLOWED_FORMATS[fmt]))
    return out


MODEL_MAX_DIM = 1024  # PRD p.5: photos resized before any model call


def resize_for_model(data: bytes, max_dim: int = MODEL_MAX_DIM) -> tuple[bytes, str]:
    """Return (JPEG bytes, mime type) no larger than max_dim on the long side,
    with EXIF orientation applied. The stored original is left untouched."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_dim, max_dim))
        out = io.BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


def save_photos(uploads_dir: Path, session_id: str, photos: list[tuple[bytes, str]]) -> list[str]:
    """Write validated photos; returns names relative to `uploads_dir`."""
    folder = uploads_dir / session_id
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for data, ext in photos:
        name = f"{uuid.uuid4().hex[:12]}.{ext}"
        (folder / name).write_bytes(data)
        names.append(f"{session_id}/{name}")
    return names


def resolve_photo(uploads_dir: Path, relative: str) -> Path:
    """Map a stored relative name back to a path, refusing anything that
    escapes the uploads folder."""
    root = uploads_dir.resolve()
    path = (root / relative).resolve()
    if root != path and root not in path.parents:
        raise bad_input("Invalid photo reference.")
    return path
