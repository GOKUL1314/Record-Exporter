from __future__ import annotations

from app.schemas import ExportFormat
from app.services.exporters.base import BaseExporter
from app.services.exporters.csv_exporter import CsvExporter
from app.services.exporters.excel_exporter import ExcelExporter
from app.services.exporters.json_exporter import JsonExporter
from app.services.exporters.pdf_exporter import PdfExporter

EXPORTERS: dict[ExportFormat, BaseExporter] = {
    "xlsx": ExcelExporter(),
    "csv": CsvExporter(),
    "json": JsonExporter(),
    "pdf": PdfExporter(),
}


def get_exporter(fmt: str) -> BaseExporter:
    normalized = (fmt or "").strip().lower()
    exporter = EXPORTERS.get(normalized)  # type: ignore[arg-type]
    if exporter is None:
        raise ValueError(f"Unsupported export format: {fmt}")
    return exporter
