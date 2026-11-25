import csv
from io import BytesIO, StringIO
import json
import zipfile

import openpyxl
from pypdf import PdfReader

from app.schemas import PageDetails, PageSection
from app.services.exporters import get_exporter
from app.services.zip_builder import build_zip


def _sample_record():
    return (
        {
            "Event Name": "SF Non-Slop Hackathon — Edition 1 ✨",
            "Host": "=CMD|'/C calc'!A0",
            "Notes": "+100 attendees\n-Bring laptop",
            "Registration Link": "https://luma.com/32d8mqid",
        },
        PageDetails(
            url="https://luma.com/32d8mqid",
            title="SF Non-Slop Hackathon · Luma",
            fetch_status="ok",
            sections=[
                PageSection(heading="About Event", content="Build thoughtfully.\n\nNo slop."),
                PageSection(heading="Prizes", content="- $1,000 cash\n- Merch"),
            ],
        ),
    )


def test_excel_exporter_sheets_formatting_and_formula_escaping():
    record, details = _sample_record()
    data = get_exporter("xlsx").export(1, record, details)

    wb = openpyxl.load_workbook(BytesIO(data))
    assert wb.sheetnames == ["Record Details", "Page Details"]

    ws_rec = wb["Record Details"]
    assert ws_rec["A1"].value == "Field"
    assert ws_rec["B1"].value == "Value"
    assert ws_rec["A1"].font.bold is True
    assert ws_rec["B2"].alignment.wrap_text is True
    # Formula injection protected
    assert ws_rec["B3"].value == "'=CMD|'/C calc'!A0"
    assert ws_rec["B4"].value.startswith("'+100")

    ws_page = wb["Page Details"]
    assert ws_page["A1"].value == "Section"
    assert ws_page["B1"].value == "Content"
    sections = {ws_page.cell(r, 1).value: ws_page.cell(r, 2).value for r in range(2, ws_page.max_row + 1)}
    assert sections["Page Title"] == "SF Non-Slop Hackathon · Luma"
    assert sections["About Event"] == "Build thoughtfully.\n\nNo slop."
    assert sections["Prizes"] == "'- $1,000 cash\n- Merch"


def test_csv_exporter_utf8_bom_and_formula_escaping():
    record, details = _sample_record()
    raw = get_exporter("csv").export(1, record, details)
    assert raw.startswith(b"\xef\xbb\xbf")

    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(StringIO(text)))
    assert rows[0] == ["Type", "Field", "Value"]
    assert ["Record", "Host", "'=CMD|'/C calc'!A0"] in rows
    assert ["Page section", "Prizes", "'- $1,000 cash\n- Merch"] in rows


def test_json_exporter_exact_schema():
    record, details = _sample_record()
    raw = get_exporter("json").export(2, record, details)
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["record_number"] == 2
    assert parsed["record"]["Event Name"] == record["Event Name"]
    assert parsed["page_details"]["url"] == "https://luma.com/32d8mqid"
    assert parsed["page_details"]["title"] == "SF Non-Slop Hackathon · Luma"
    assert parsed["page_details"]["fetch_status"] == "ok"
    assert parsed["page_details"]["sections"][0]["heading"] == "About Event"


def test_pdf_exporter_unicode_and_page_numbers():
    record, details = _sample_record()
    raw = get_exporter("pdf").export(1, record, details)
    reader = PdfReader(BytesIO(raw))
    assert len(reader.pages) >= 1
    page_text = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "Record 1" in page_text
    assert "SF Non-Slop Hackathon" in page_text
    assert "About Event" in page_text
    assert "Page 1" in page_text


def test_zip_builder():
    zbytes = build_zip([("1.json", b"{}"), ("2.json", b"{}")])
    with zipfile.ZipFile(BytesIO(zbytes)) as zf:
        assert zf.namelist() == ["1.json", "2.json"]
