from __future__ import annotations

import csv
from io import StringIO

from app.schemas import PageDetails
from app.services.exporters.base import BaseExporter, sanitize_spreadsheet_value


class CsvExporter(BaseExporter):
    extension = "csv"
    media_type = "text/csv; charset=utf-8"

    def export(
        self,
        record_number: int,
        record: dict[str, str],
        page_details: PageDetails,
    ) -> bytes:
        buf = StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerow(["Type", "Field", "Value"])

        for field_name, field_val in record.items():
            writer.writerow(
                [
                    "Record",
                    sanitize_spreadsheet_value(field_name),
                    sanitize_spreadsheet_value(field_val),
                ]
            )

        if page_details.url:
            writer.writerow(
                ["Page section", "URL", sanitize_spreadsheet_value(page_details.url)]
            )
        if page_details.title:
            writer.writerow(
                [
                    "Page section",
                    "Page Title",
                    sanitize_spreadsheet_value(page_details.title),
                ]
            )
        if page_details.fetch_status.startswith("Could not fetch:"):
            writer.writerow(
                [
                    "Page section",
                    "Status",
                    sanitize_spreadsheet_value(page_details.fetch_status),
                ]
            )

        for sec in page_details.sections:
            writer.writerow(
                [
                    "Page section",
                    sanitize_spreadsheet_value(sec.heading),
                    sanitize_spreadsheet_value(sec.content),
                ]
            )

        return buf.getvalue().encode("utf-8-sig")
