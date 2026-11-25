from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
import re
from typing import Any

import openpyxl
import xlrd

from app.config import DEFAULT_SHEET_NAME

_URL_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)
_TIME_FORMAT_HINT_RE = re.compile(r"[hs]", re.IGNORECASE)
_DATE_FORMAT_HINT_RE = re.compile(r"[dy]", re.IGNORECASE)


@dataclass
class SheetData:
    sheet_name: str
    columns: list[str]
    rows: list[dict[str, str]]
    detected_link_column: str | None


@dataclass
class WorkbookInfo:
    sheets: list[str]
    default_sheet: str
    active_sheet_data: SheetData


def _format_datetime(value: datetime, number_format: str | None = None) -> str:
    fmt = (number_format or "").strip()
    # Excel uses 1899-12-30 as the zero-date sentinel for time-only values.
    is_sentinel_date = value.year == 1899 and value.month == 12 and value.day == 30
    has_time_hint = bool(_TIME_FORMAT_HINT_RE.search(fmt))
    has_date_hint = bool(_DATE_FORMAT_HINT_RE.search(fmt))

    if is_sentinel_date or (has_time_hint and not has_date_hint):
        return value.strftime("%H:%M")
    if value.hour == 0 and value.minute == 0 and value.second == 0:
        return value.strftime("%d-%m-%Y")
    return value.strftime("%d-%m-%Y %H:%M")


def _format_cell_value(value: Any, number_format: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return _format_datetime(value, number_format)
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def _normalize_headers(raw_headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    for idx, raw in enumerate(raw_headers, start=1):
        base = raw.strip() if raw else f"Column {idx}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        headers.append(base if count == 1 else f"{base} ({count})")
    return headers


def _trim_empty_grid(grid: list[list[str]]) -> list[list[str]]:
    if not grid:
        return []

    # Trim trailing completely empty rows (keep header row at index 0 if present).
    last_non_empty_row = -1
    for r_idx, row in enumerate(grid):
        if any(cell != "" for cell in row):
            last_non_empty_row = r_idx
    if last_non_empty_row == -1:
        return []
    grid = grid[: last_non_empty_row + 1]

    # Trim trailing completely empty columns across header + data rows.
    max_cols = max((len(r) for r in grid), default=0)
    last_non_empty_col = -1
    for c_idx in range(max_cols):
        if any(c_idx < len(row) and row[c_idx] != "" for row in grid):
            last_non_empty_col = c_idx
    if last_non_empty_col == -1:
        return []

    return [
        [row[c] if c < len(row) else "" for c in range(last_non_empty_col + 1)]
        for row in grid
    ]


def _grid_to_sheet_data(sheet_name: str, raw_grid: list[list[str]]) -> SheetData:
    grid = _trim_empty_grid(raw_grid)
    if not grid:
        return SheetData(
            sheet_name=sheet_name,
            columns=[],
            rows=[],
            detected_link_column=None,
        )

    columns = _normalize_headers(grid[0])
    rows: list[dict[str, str]] = []
    for raw_row in grid[1:]:
        row_dict = {
            col: (raw_row[i] if i < len(raw_row) else "")
            for i, col in enumerate(columns)
        }
        rows.append(row_dict)

    detected = detect_link_column(columns, rows)
    return SheetData(
        sheet_name=sheet_name,
        columns=columns,
        rows=rows,
        detected_link_column=detected,
    )


def detect_link_column(columns: list[str], rows: list[dict[str, str]]) -> str | None:
    """Auto-detect the column holding target page links.

    Prefers headers containing 'registration', 'link', or 'url', and avoids
    headers containing 'source'. Returns None if no column looks like a link column.
    """
    best_col: str | None = None
    best_score = 0
    sample = rows[:20]

    for col in columns:
        header_lower = col.lower()
        if "source" in header_lower:
            continue

        score = 0
        if "registration" in header_lower:
            score += 10
        if "link" in header_lower:
            score += 6
        if "url" in header_lower:
            score += 6

        has_url_value = any(
            _URL_PREFIX_RE.match(row.get(col, "")) for row in sample
        )
        if has_url_value:
            score += 3

        if score > best_score:
            best_score = score
            best_col = col

    return best_col if best_score >= 3 else None


def choose_default_sheet(sheet_names: list[str]) -> str:
    if not sheet_names:
        raise ValueError("The workbook contains no sheets.")
    if DEFAULT_SHEET_NAME in sheet_names:
        return DEFAULT_SHEET_NAME
    for name in sheet_names:
        if name.strip().lower() == DEFAULT_SHEET_NAME.lower():
            return name
    return sheet_names[0]


def _read_xlsx_sheet(wb: openpyxl.Workbook, sheet_name: str) -> SheetData:
    ws = wb[sheet_name]
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    if max_row == 0 or max_col == 0:
        return SheetData(sheet_name=sheet_name, columns=[], rows=[], detected_link_column=None)

    merged_map: dict[tuple[int, int], tuple[int, int]] = {}
    for rng in ws.merged_cells.ranges:
        top_left = (rng.min_row, rng.min_col)
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                merged_map[(r, c)] = top_left

    grid: list[list[str]] = []
    for r in range(1, max_row + 1):
        row_vals: list[str] = []
        for c in range(1, max_col + 1):
            tr, tc = merged_map.get((r, c), (r, c))
            cell = ws.cell(row=tr, column=tc)
            val = cell.value
            if (val is None or str(val).strip() == "") and cell.hyperlink and cell.hyperlink.target:
                val = cell.hyperlink.target
            row_vals.append(_format_cell_value(val, cell.number_format))
        grid.append(row_vals)

    return _grid_to_sheet_data(sheet_name, grid)


def _format_xls_cell(wb: xlrd.Book, cell: xlrd.sheet.Cell) -> str:
    ctype = cell.ctype
    val = cell.value
    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return ""
    if ctype == xlrd.XL_CELL_DATE:
        y, m, d, hour, minute, _sec = xlrd.xldate_as_tuple(val, wb.datemode)
        if (y, m, d) == (0, 0, 0):
            return f"{hour:02d}:{minute:02d}"
        if hour == 0 and minute == 0:
            return f"{d:02d}-{m:02d}-{y:04d}"
        return f"{d:02d}-{m:02d}-{y:04d} {hour:02d}:{minute:02d}"
    if ctype == xlrd.XL_CELL_NUMBER:
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
        return str(val)
    if ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if val else "FALSE"
    return str(val).strip()


def _read_xls_sheet(wb: xlrd.Book, sheet_name: str) -> SheetData:
    ws = wb.sheet_by_name(sheet_name)
    if ws.nrows == 0 or ws.ncols == 0:
        return SheetData(sheet_name=sheet_name, columns=[], rows=[], detected_link_column=None)

    merged_map: dict[tuple[int, int], tuple[int, int]] = {}
    for rlo, rhi, clo, chi in getattr(ws, "merged_cells", []):
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                merged_map[(r, c)] = (rlo, clo)

    grid: list[list[str]] = []
    for r in range(ws.nrows):
        row_vals: list[str] = []
        for c in range(ws.ncols):
            tr, tc = merged_map.get((r, c), (r, c))
            row_vals.append(_format_xls_cell(wb, ws.cell(tr, tc)))
        grid.append(row_vals)

    return _grid_to_sheet_data(sheet_name, grid)


def get_sheet_names(file_path: Path) -> list[str]:
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()
    if suffix == ".xls":
        wb = xlrd.open_workbook(str(file_path), on_demand=True)
        try:
            return list(wb.sheet_names())
        finally:
            wb.release_resources()
    raise ValueError(f"Unsupported file format: {suffix}")


def read_sheet(file_path: Path, sheet_name: str) -> SheetData:
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        wb = openpyxl.load_workbook(file_path, data_only=True)
        try:
            if sheet_name not in wb.sheetnames:
                raise ValueError(f"Sheet '{sheet_name}' was not found in the workbook.")
            return _read_xlsx_sheet(wb, sheet_name)
        finally:
            wb.close()

    if suffix == ".xls":
        try:
            wb = xlrd.open_workbook(str(file_path), formatting_info=True)
        except NotImplementedError:
            wb = xlrd.open_workbook(str(file_path), formatting_info=False)
        try:
            if sheet_name not in wb.sheet_names():
                raise ValueError(f"Sheet '{sheet_name}' was not found in the workbook.")
            return _read_xls_sheet(wb, sheet_name)
        finally:
            wb.release_resources()

    raise ValueError(f"Unsupported file format: {suffix}")


def inspect_workbook(file_path: Path) -> WorkbookInfo:
    sheets = get_sheet_names(file_path)
    default_sheet = choose_default_sheet(sheets)
    sheet_data = read_sheet(file_path, default_sheet)
    return WorkbookInfo(
        sheets=sheets,
        default_sheet=default_sheet,
        active_sheet_data=sheet_data,
    )
