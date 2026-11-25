from __future__ import annotations

import json

from app.schemas import PageDetails
from app.services.exporters.base import BaseExporter


class JsonExporter(BaseExporter):
    extension = "json"
    media_type = "application/json; charset=utf-8"

    def export(
        self,
        record_number: int,
        record: dict[str, str],
        page_details: PageDetails,
    ) -> bytes:
        payload = {
            "record_number": record_number,
            "record": record,
            "page_details": {
                "url": page_details.url,
                "title": page_details.title,
                "fetch_status": page_details.fetch_status,
                "sections": [
                    {"heading": sec.heading, "content": sec.content}
                    for sec in page_details.sections
                ],
            },
        }
        return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
