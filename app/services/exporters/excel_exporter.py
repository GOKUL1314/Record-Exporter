from __future__ import annotations

from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from app.schemas import PageDetails
from app.services.exporters.base import BaseExporter, sanitize_spreadsheet_value


class ExcelExporter(BaseExporter):
    extension = "xlsx"
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def export(
        self,
        record_number: int,
        record: dict[str, str],
        page_details: PageDetails,
    ) -> bytes:
        wb = openpyxl.Workbook()
        header_font = Font(bold=True)
        header_fill = PatternFill(start_color="EEF2F7", end_color="EEF2F7", fill_type="solid")
        wrap_top = Alignment(vertical="top", wrap_text=True)

        # Sheet 1: Record Details
        ws_rec = wb.active
        ws_rec.title = "Record Details"
        ws_rec.append(["Field", "Value"])
        for cell in ws_rec[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = wrap_top

        for field_name, field_val in record.items():
            row_idx = ws_rec.max_row + 1
            c1 = ws_rec.cell(row=row_idx, column=1, value=sanitize_spreadsheet_value(field_name))
            c2 = ws_rec.cell(row=row_idx, column=2, value=sanitize_spreadsheet_value(field_val))
            c1.data_type = "s"
            c2.data_type = "s"
            c1.alignment = wrap_top
            c2.alignment = wrap_top

        ws_rec.column_dimensions["A"].width = 28
        ws_rec.column_dimensions["B"].width = 80

        # Sheet 2: Page Details
        ws_page = wb.create_sheet("Page Details")
        ws_page.append(["Section", "Content"])
        for cell in ws_page[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = wrap_top

        page_rows: list[tuple[str, str]] = []
        if page_details.url:
            page_rows.append(("URL", page_details.url))
        if page_details.title:
            page_rows.append(("Page Title", page_details.title))
        if page_details.fetch_status.startswith("Could not fetch:"):
            page_rows.append(("Status", page_details.fetch_status))
        for sec in page_details.sections:
            page_rows.append((sec.heading, sec.content))

        if not page_rows:
            page_rows.append(("Status", "No page details available"))

        for section_name, section_content in page_rows:
            row_idx = ws_page.max_row + 1
            c1 = ws_page.cell(row=row_idx, column=1, value=sanitize_spreadsheet_value(section_name))
            c2 = ws_page.cell(row=row_idx, column=2, value=sanitize_spreadsheet_value(section_content))
            c1.data_type = "s"
            c2.data_type = "s"
            c1.alignment = wrap_top
            c2.alignment = wrap_top

        ws_page.column_dimensions["A"].width = 28
        ws_page.column_dimensions["B"].width = 90

        buf = BytesIO()
        wb.save(buf)
        wb.close()
        return buf.getvalue()
