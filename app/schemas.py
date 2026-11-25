from typing import Any, Literal
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    sheets: list[str]
    default_sheet: str
    total_records: int
    columns: list[str]
    detected_link_column: str | None = None
    preview_rows: list[dict[str, str]]


class SheetInfoRequest(BaseModel):
    session_id: str
    sheet_name: str


class SheetInfoResponse(BaseModel):
    sheet_name: str
    total_records: int
    columns: list[str]
    detected_link_column: str | None = None
    preview_rows: list[dict[str, str]]


class RecordsRequest(BaseModel):
    session_id: str
    sheet_name: str
    selection: str
    link_column: str | None = None


class RecordItem(BaseModel):
    record_number: int
    fields: dict[str, str]
    link_url: str | None = None


class RecordsResponse(BaseModel):
    session_id: str
    sheet_name: str
    columns: list[str]
    link_column: str | None = None
    records: list[RecordItem]


class DetailsRequest(BaseModel):
    session_id: str
    sheet_name: str
    record_numbers: list[int] = Field(..., min_length=1)
    link_column: str | None = None


class PageSection(BaseModel):
    heading: str
    content: str


class PageDetails(BaseModel):
    url: str = ""
    title: str = ""
    fetch_status: str = "skipped"
    sections: list[PageSection] = Field(default_factory=list)


class DownloadRequest(BaseModel):
    session_id: str
    sheet_name: str
    record_numbers: list[int] = Field(..., min_length=1)
    link_column: str | None = None


ExportFormat = Literal["xlsx", "csv", "json", "pdf"]
