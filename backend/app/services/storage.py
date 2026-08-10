from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile


class UnsupportedFileTypeError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    extension: str
    size_bytes: int
    sha256: str


async def store_upload(
    upload: UploadFile,
    *,
    destination_dir: Path,
    document_id: str,
    allowed_extensions: tuple[str, ...],
    max_bytes: int,
) -> StoredUpload:
    filename = upload.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in allowed_extensions:
        allowed = ", ".join(allowed_extensions)
        raise UnsupportedFileTypeError(f"Unsupported file type. Allowed: {allowed}")

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{document_id}{extension}"

    digest = hashlib.sha256()
    total = 0

    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLargeError(f"File exceeds the {max_bytes} byte upload limit")
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredUpload(
        path=destination,
        extension=extension,
        size_bytes=total,
        sha256=digest.hexdigest(),
    )
