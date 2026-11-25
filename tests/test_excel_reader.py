from datetime import date, datetime, time
from pathlib import Path

import openpyxl
import xlwt

from app.services.excel_reader import inspect_workbook, read_sheet


def test_xlsx_default_sheet_dates_merged_blank_headers_and_duplicates(tmp_path: Path):
    file_path = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()

    ws_first = wb.active
    ws_first.title = "Day 1"
    ws_first.append(["Title", "Source URL"])
    ws_first.append(["Event A", "https://example.com/source"])

    ws_all = wb.create_sheet("All Data")
    ws_all.append(["Event Name", "Date", "Time", None, "Registration Link", "Source Website"])
    ws_all.append([
        "Hackathon",
        datetime(2026, 11, 25, 0, 0, 0),
        time(18, 30),
        "Note 1",
        "https://luma.com/abc",
        "https://luma.com/sf",
    ])
    # Exact duplicate row should be preserved.
    ws_all.append([
        "Hackathon",
        date(2026, 11, 25),
        time(18, 30),
        "Note 1",
        "https://luma.com/abc",
        "https://luma.com/sf",
    ])
    # Row with merged cell across A4:B4
    ws_all.append(["Merged Event", None, time(9, 0), None, "", ""])
    ws_all.merge_cells("A4:B4")

    wb.save(file_path)

    info = inspect_workbook(file_path)
    assert info.sheets == ["Day 1", "All Data"]
    assert info.default_sheet == "All Data"

    data = info.active_sheet_data
    assert data.columns == [
        "Event Name",
        "Date",
        "Time",
        "Column 4",
        "Registration Link",
        "Source Website",
    ]
    assert data.detected_link_column == "Registration Link"
    assert len(data.rows) == 3

    assert data.rows[0]["Date"] == "25-11-2026"
    assert data.rows[0]["Time"] == "18:30"
    assert data.rows[0]["Column 4"] == "Note 1"
    # Duplicate kept
    assert data.rows[1]["Event Name"] == "Hackathon"
    # Merged value propagated
    assert data.rows[2]["Event Name"] == "Merged Event"
    assert data.rows[2]["Date"] == "Merged Event"
    assert data.rows[2]["Time"] == "09:00"


def test_xlsx_no_link_column_and_avoids_source(tmp_path: Path):
    file_path = tmp_path / "no_links.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contacts"
    ws.append(["Name", "City", "Source Link"])
    ws.append(["Alice", "SF", "https://example.com/src"])
    wb.save(file_path)

    info = inspect_workbook(file_path)
    assert info.default_sheet == "Contacts"
    assert info.active_sheet_data.detected_link_column is None


def test_xls_reader_supports_legacy_format(tmp_path: Path):
    file_path = tmp_path / "legacy.xls"
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Events")
    ws.write(0, 0, "Name")
    ws.write(0, 1, "Date")
    ws.write(0, 2, "Event URL")

    date_style = xlwt.XFStyle()
    date_style.num_format_str = "YYYY-MM-DD"
    ws.write(1, 0, "Demo Day")
    ws.write(1, 1, date(2026, 12, 1), date_style)
    ws.write(1, 2, "https://example.com/demo")
    wb.save(str(file_path))

    data = read_sheet(file_path, "Events")
    assert data.columns == ["Name", "Date", "Event URL"]
    assert data.detected_link_column == "Event URL"
    assert data.rows[0]["Name"] == "Demo Day"
    assert data.rows[0]["Date"] == "01-12-2026"
