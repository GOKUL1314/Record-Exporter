from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import FONTS_DIR
from app.schemas import PageDetails
from app.services.exporters.base import BaseExporter

_FONT_REGULAR = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"
_FONTS_REGISTERED = False


def _ensure_fonts() -> tuple[str, str]:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return _FONT_REGULAR, _FONT_BOLD

    regular_path = FONTS_DIR / "DejaVuSans.ttf"
    bold_path = FONTS_DIR / "DejaVuSans-Bold.ttf"
    if not regular_path.exists():
        raise FileNotFoundError(f"Bundled font not found: {regular_path}")

    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(regular_path)))
    if bold_path.exists():
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold_path)))
        pdfmetrics.registerFontFamily(
            _FONT_REGULAR, normal=_FONT_REGULAR, bold=_FONT_BOLD
        )
        bold_name = _FONT_BOLD
    else:
        bold_name = _FONT_REGULAR

    _FONTS_REGISTERED = True
    return _FONT_REGULAR, bold_name


def _html_text(text: str) -> str:
    escaped = escape(text or "")
    return escaped.replace("\r\n", "\n").replace("\n", "<br/>")


def _draw_page_number(canvas, doc) -> None:
    canvas.saveState()
    font_name, _ = _ensure_fonts()
    canvas.setFont(font_name, 9)
    canvas.setFillColor(colors.HexColor("#64748B"))
    page_text = f"Page {doc.page}"
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, page_text)
    canvas.restoreState()


class PdfExporter(BaseExporter):
    extension = "pdf"
    media_type = "application/pdf"

    def export(
        self,
        record_number: int,
        record: dict[str, str],
        page_details: PageDetails,
    ) -> bytes:
        font_regular, font_bold = _ensure_fonts()

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=20 * mm,
            title=f"Record {record_number}",
        )

        base_styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "RecordTitle",
            parent=base_styles["Title"],
            fontName=font_bold,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0F172A"),
            alignment=0,
            spaceAfter=10,
        )
        section_header_style = ParagraphStyle(
            "SectionBanner",
            parent=base_styles["Heading2"],
            fontName=font_bold,
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=12,
            spaceAfter=6,
        )
        sub_heading_style = ParagraphStyle(
            "PageSubHeading",
            parent=base_styles["Heading3"],
            fontName=font_bold,
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#1D4ED8"),
            spaceBefore=8,
            spaceAfter=3,
        )
        body_style = ParagraphStyle(
            "BodyTextUnicode",
            parent=base_styles["BodyText"],
            fontName=font_regular,
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1E293B"),
            splitLongWords=1,
            spaceAfter=6,
        )
        cell_key_style = ParagraphStyle(
            "CellKey",
            fontName=font_bold,
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#0F172A"),
            splitLongWords=1,
        )
        cell_val_style = ParagraphStyle(
            "CellVal",
            fontName=font_regular,
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            splitLongWords=1,
        )
        table_header_style = ParagraphStyle(
            "TableHeader",
            fontName=font_bold,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
        )

        story = [Paragraph(f"Record {record_number}", title_style)]

        # Field/Value table
        table_data = [
            [
                Paragraph("Field", table_header_style),
                Paragraph("Value", table_header_style),
            ]
        ]
        for field_name, field_val in record.items():
            table_data.append(
                [
                    Paragraph(_html_text(field_name), cell_key_style),
                    Paragraph(_html_text(field_val or "-"), cell_val_style),
                ]
            )

        avail_width = A4[0] - 36 * mm
        col_widths = [avail_width * 0.30, avail_width * 0.70]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

        # Page details section
        story.append(Paragraph("Details from the event page", section_header_style))

        if page_details.url:
            story.append(
                Paragraph(
                    f"<b>URL:</b> {_html_text(page_details.url)}",
                    body_style,
                )
            )
        if page_details.title:
            story.append(
                Paragraph(
                    f"<b>Page Title:</b> {_html_text(page_details.title)}",
                    body_style,
                )
            )

        if page_details.fetch_status.startswith("Could not fetch:"):
            story.append(Paragraph(_html_text(page_details.fetch_status), body_style))
        elif page_details.sections:
            for sec in page_details.sections:
                story.append(Paragraph(_html_text(sec.heading), sub_heading_style))
                story.append(Paragraph(_html_text(sec.content), body_style))
        elif page_details.fetch_status == "skipped":
            story.append(Paragraph("No page link provided for this record.", body_style))
        else:
            story.append(Paragraph("No additional sections extracted.", body_style))

        doc.build(story, onFirstPage=_draw_page_number, onLaterPages=_draw_page_number)
        return buf.getvalue()
