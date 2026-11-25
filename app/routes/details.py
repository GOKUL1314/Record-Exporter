from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import MAX_RECORDS_PER_REQUEST, NO_LINK_COLUMN_VALUE
from app.schemas import DetailsRequest, PageDetails
from app.services.page_scraper import fetch_many_page_details
from app.services.session_store import session_store

router = APIRouter()


def _validate_record_numbers(record_numbers: list[int], total_records: int) -> list[int]:
    if len(record_numbers) > MAX_RECORDS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_RECORDS_PER_REQUEST} records allowed per request.",
        )
    deduped: list[int] = []
    seen: set[int] = set()
    for num in record_numbers:
        if num < 1 or num > total_records:
            raise HTTPException(
                status_code=400,
                detail=f"Record {num} is out of range (1-{total_records}).",
            )
        if num not in seen:
            seen.add(num)
            deduped.append(num)
    return deduped


@router.post("/details")
async def stream_details(req: DetailsRequest) -> StreamingResponse:
    try:
        sheet = session_store.get_sheet_data(req.session_id, req.sheet_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_numbers = _validate_record_numbers(req.record_numbers, len(sheet.rows))

    link_col = req.link_column
    if link_col in (None, "", NO_LINK_COLUMN_VALUE):
        link_col = None
    elif link_col not in sheet.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Link column '{link_col}' does not exist in sheet '{sheet.sheet_name}'.",
        )

    items: list[tuple[int, str]] = [
        (rec_num, sheet.rows[rec_num - 1].get(link_col, "").strip() if link_col else "")
        for rec_num in record_numbers
    ]

    async def event_stream():
        if link_col is None:
            total = len(items)
            for idx, (rec_num, _) in enumerate(items, start=1):
                skipped = PageDetails(url="", title="", fetch_status="skipped", sections=[])
                payload = {
                    "type": "progress",
                    "completed": idx,
                    "total": total,
                    "record_number": rec_num,
                    "details": skipped.model_dump(),
                }
                yield json.dumps(payload, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done", "total": total}) + "\n"
            return

        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def on_progress(
            completed: int, total: int, rec_num: int, details: PageDetails
        ) -> None:
            await queue.put(
                {
                    "type": "progress",
                    "completed": completed,
                    "total": total,
                    "record_number": rec_num,
                    "details": details.model_dump(),
                }
            )

        async def runner() -> None:
            try:
                await fetch_many_page_details(
                    items,
                    get_cached=lambda u: session_store.get_cached_page_details(
                        req.session_id, u
                    ),
                    set_cached=lambda u, d: session_store.set_cached_page_details(
                        req.session_id, u, d
                    ),
                    on_progress=on_progress,
                )
            finally:
                await queue.put({"type": "done", "total": len(items)})
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield json.dumps(item, ensure_ascii=False) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
