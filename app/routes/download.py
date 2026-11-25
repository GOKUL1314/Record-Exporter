from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import MAX_RECORDS_PER_REQUEST, NO_LINK_COLUMN_VALUE
from app.schemas import DownloadRequest, PageDetails
from app.services.exporters import get_exporter
from app.services.page_scraper import fetch_many_page_details
from app.services.session_store import session_store
from app.services.zip_builder import build_zip

router = APIRouter()


@router.post("/download/{fmt}")
async def download_records(fmt: str, req: DownloadRequest) -> Response:
    try:
        exporter = get_exporter(fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        sheet = session_store.get_sheet_data(req.session_id, req.sheet_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if len(req.record_numbers) > MAX_RECORDS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_RECORDS_PER_REQUEST} records allowed per request.",
        )

    record_numbers: list[int] = []
    seen: set[int] = set()
    for num in req.record_numbers:
        if num < 1 or num > len(sheet.rows):
            raise HTTPException(
                status_code=400,
                detail=f"Record {num} is out of range (1-{len(sheet.rows)}).",
            )
        if num not in seen:
            seen.add(num)
            record_numbers.append(num)

    link_col = req.link_column
    if link_col in (None, "", NO_LINK_COLUMN_VALUE):
        link_col = None
    elif link_col not in sheet.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Link column '{link_col}' does not exist in sheet '{sheet.sheet_name}'.",
        )

    # Fetch any uncached URLs once; cached URLs are served immediately without refetching.
    details_by_record: dict[int, PageDetails] = {}
    missing_items: list[tuple[int, str]] = []

    for rec_num in record_numbers:
        row = sheet.rows[rec_num - 1]
        url = row.get(link_col, "").strip() if link_col else ""
        if not url:
            details_by_record[rec_num] = PageDetails(
                url="", title="", fetch_status="skipped", sections=[]
            )
            continue
        cached = session_store.get_cached_page_details(req.session_id, url)
        if cached is not None:
            details_by_record[rec_num] = cached
        else:
            missing_items.append((rec_num, url))

    if missing_items:
        fetched = await fetch_many_page_details(
            missing_items,
            get_cached=lambda u: session_store.get_cached_page_details(req.session_id, u),
            set_cached=lambda u, d: session_store.set_cached_page_details(
                req.session_id, u, d
            ),
        )
        details_by_record.update(fetched)

    rendered_files: list[tuple[str, bytes]] = []
    for rec_num in record_numbers:
        row = sheet.rows[rec_num - 1]
        page_details = details_by_record[rec_num]
        content = exporter.export(rec_num, row, page_details)
        rendered_files.append((f"{rec_num}.{exporter.extension}", content))

    if len(rendered_files) == 1:
        filename, content = rendered_files[0]
        return Response(
            content=content,
            media_type=exporter.media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    zip_bytes = build_zip(rendered_files)
    zip_name = f"records_{exporter.extension}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )
