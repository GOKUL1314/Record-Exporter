from __future__ import annotations

from io import BytesIO
import zipfile


def build_zip(files: list[tuple[str, bytes]]) -> bytes:
    """Bundle (filename, bytes) pairs into an in-memory ZIP archive."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files:
            zf.writestr(filename, content)
    return buf.getvalue()
