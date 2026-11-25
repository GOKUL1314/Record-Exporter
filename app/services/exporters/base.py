from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import PageDetails

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def sanitize_spreadsheet_value(value: str | None) -> str:
    """Prefix values starting with =, +, -, or @ with a single quote to prevent formula injection."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


class BaseExporter(ABC):
    extension: str
    media_type: str

    @abstractmethod
    def export(
        self,
        record_number: int,
        record: dict[str, str],
        page_details: PageDetails,
    ) -> bytes:
        """Render a single record and its page details to file bytes."""
