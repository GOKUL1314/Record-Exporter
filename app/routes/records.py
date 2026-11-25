from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import NO_LINK_COLUMN_VALUE
from app.schemas import RecordItem, RecordsRequest, RecordsResponse
from app.services.record_selector import parse_record_selection
from app.services.session_store import session_store

router = APIRouter()


@router.post("/records", response_model=RecordsResponse)
async def get_records(req: RecordsRequest) -> RecordsResponse:
    try:
        sheet = session_store.get_sheet_data(req.session_id, req.sheet_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        selected_numbers = parse_record_selection(req.selection, len(sheet.rows))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    link_col = req.link_column
    if link_col in (None, "", NO_LINK_COLUMN_VALUE):
        link_col = None
    elif link_col not in sheet.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Link column '{link_col}' does not exist in sheet '{sheet.sheet_name}'.",
        )

    items: list[RecordItem] = []
    for rec_num in selected_numbers:
        row = sheet.rows[rec_num - 1]
        link_url = row.get(link_col, "").strip() if link_col else None
        items.append(
            RecordItem(
                record_number=rec_num,
                fields=row,
                link_url=link_url or None,
            )
        )

    return RecordsResponse(
        session_id=req.session_id,
        sheet_name=sheet.sheet_name,
        columns=sheet.columns,
        link_column=link_col,
        records=items,
    )
