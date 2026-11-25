from __future__ import annotations

from pathlib import Path
import re
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, UPLOADS_DIR
from app.schemas import SheetInfoRequest, SheetInfoResponse, UploadResponse
from app.services.session_store import session_store

router = APIRouter()

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(raw_name: str | None) -> str:
    base = Path(raw_name or "upload.xlsx").name
    cleaned = _SAFE_FILENAME_RE.sub("_", base).strip("._")
    return cleaned or "upload.xlsx"


@router.post("/upload", response_model=UploadResponse)
async def upload_excel(file: UploadFile = File(...)) -> UploadResponse:
    original_name = Path(file.filename or "upload.xlsx").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload an .xlsx or .xls file.",
        )

    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="File is too large. Maximum allowed size is 10 MB.",
            )
        chunks.append(chunk)

    if total_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(original_name)
    stored_path = UPLOADS_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    stored_path.write_bytes(b"".join(chunks))

    try:
        session = session_store.create_session(original_name, stored_path)
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Could not read Excel file: {exc}",
        ) from exc

    active = session.parsed_sheets[session.default_sheet]
    return UploadResponse(
        session_id=session.session_id,
        filename=session.filename,
        sheets=session.sheets,
        default_sheet=session.default_sheet,
        total_records=len(active.rows),
        columns=active.columns,
        detected_link_column=active.detected_link_column,
        preview_rows=active.rows[:5],
    )


@router.post("/sheet", response_model=SheetInfoResponse)
async def select_sheet(req: SheetInfoRequest) -> SheetInfoResponse:
    try:
        sheet_data = session_store.get_sheet_data(req.session_id, req.sheet_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SheetInfoResponse(
        sheet_name=sheet_data.sheet_name,
        total_records=len(sheet_data.rows),
        columns=sheet_data.columns,
        detected_link_column=sheet_data.detected_link_column,
        preview_rows=sheet_data.rows[:5],
    )
