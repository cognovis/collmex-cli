"""ReportLab renderer for cognovis customer invoice PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from .config import CollmexConfig, get_config


@dataclass
class InvoiceLineItem:
    """A preformatted invoice line item."""

    name: str
    quantity: str
    unit_price: str
    amount: str


@dataclass
class InvoiceData:
    """Structured data needed to render a cognovis customer invoice."""

    company_name: str
    company_contact_name: str | None
    address_line1: str
    postal_code: str
    city: str
    country: str
    vat_number: str | None
    invoice_nr: str
    invoice_date: str
    delivery_date: str | None
    project_ref: str | None
    line_items: list[InvoiceLineItem]
    subtotal: str
    vat_rate: str
    vat_amount: str
    total: str
    cost_note: str | None = None
    vat_note: str | None = None
    due_date: str | None = None


def validate_seller_config(config: CollmexConfig) -> None:
    """Raise ValueError with a clear message if mandatory seller fields are missing."""
    missing = config.validate_seller_fields()
    if missing:
        raise ValueError(
            f"Missing mandatory seller fields in config: {', '.join(missing)}. "
            f"Set COLLMEX_SELLER_NAME, COLLMEX_SELLER_STREET, COLLMEX_SELLER_ZIP, "
            f"COLLMEX_SELLER_CITY, COLLMEX_SELLER_VAT_ID, COLLMEX_SELLER_HRB, "
            f"COLLMEX_SELLER_IBAN, COLLMEX_SELLER_BIC."
        )


def render_invoice_pdf(
    invoice_data: InvoiceData,
    config: CollmexConfig | None = None,
    output_path: Path | None = None,
    logo_path: Path | None = None,
) -> bytes:
    """Render a cognovis-branded invoice PDF."""
    seller_config = config or get_config()
    validate_seller_config(seller_config)

    resolved_logo_path = logo_path or _default_logo_path()
    pdf_bytes = _render_reportlab_pdf(invoice_data, seller_config, resolved_logo_path)

    if output_path is not None:
        output_path.write_bytes(pdf_bytes)
    return pdf_bytes


def _default_logo_path() -> Path:
    return Path(__file__).parent / "assets" / "cognovis_logo.png"


def _render_reportlab_pdf(invoice_data: InvoiceData, config: CollmexConfig, logo_path: Path) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    width, height = A4

    _draw_header(pdf, width, height, config, logo_path)
    table_top = _draw_recipient_and_metadata(pdf, width, height, invoice_data)
    table_bottom = _draw_line_items(pdf, table_top, invoice_data)
    _draw_notes(pdf, table_bottom, invoice_data)
    _draw_footer(pdf, config)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _draw_header(pdf: canvas.Canvas, width: float, height: float, config: CollmexConfig, logo_path: Path) -> None:
    if logo_path.exists():
        logo_width = 55 * mm
        logo_height = logo_width * 197 / 558
        pdf.drawImage(
            ImageReader(str(logo_path)),
            width - 25 * mm - logo_width,
            height - 28 * mm,
            width=logo_width,
            height=logo_height,
            mask="auto",
        )

    sender = (
        f"{config.seller_name} - project management solutions - "
        f"{config.seller_street} - {config.seller_zip} {config.seller_city}"
    )
    pdf.setFont("Helvetica-Bold", 7)
    pdf.setFillGray(0.55)
    pdf.drawString(25 * mm, height - 47 * mm, sender)
    pdf.setFillGray(0)


def _draw_recipient_and_metadata(
    pdf: canvas.Canvas,
    width: float,
    height: float,
    invoice_data: InvoiceData,
) -> float:
    recipient_y = height - 57 * mm
    recipient_lines = [
        invoice_data.company_name,
        invoice_data.company_contact_name,
        invoice_data.address_line1,
        f"{invoice_data.postal_code} {invoice_data.city}",
        _display_customer_country(invoice_data.country),
        _prefixed("USt-IdNr.: ", invoice_data.vat_number),
    ]

    pdf.setFont("Helvetica", 11)
    for line in _present(recipient_lines):
        pdf.drawString(25 * mm, recipient_y, line)
        recipient_y -= 6 * mm

    title_y = min(recipient_y - 6 * mm, height - 98 * mm)
    pdf.setFont("Helvetica", 11)
    pdf.drawRightString(width - 25 * mm, title_y + 8 * mm, invoice_data.invoice_date)

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(25 * mm, title_y, f"Rechnung {invoice_data.invoice_nr}")

    detail_y = title_y - 8 * mm
    pdf.setFont("Helvetica", 11)
    if invoice_data.delivery_date:
        pdf.drawString(25 * mm, detail_y, f"Lieferdatum: {invoice_data.delivery_date}")
        detail_y -= 9 * mm

    return detail_y - 2 * mm


def _draw_line_items(pdf: canvas.Canvas, table_top: float, invoice_data: InvoiceData) -> float:
    max_items = 8
    if len(invoice_data.line_items) > max_items:
        raise ValueError(
            f"Invoice has {len(invoice_data.line_items)} line items but single-page renderer "
            f"supports at most {max_items}. Split into multiple invoices."
        )

    left = 25 * mm
    column_widths = [99.1 * mm, 15.0 * mm, 22.9 * mm, 26.3 * mm]
    row_height = 10 * mm
    header_height = 11 * mm
    summary_height = 9.5 * mm
    xs = [left]
    for column_width in column_widths:
        xs.append(xs[-1] + column_width)

    y = table_top
    _draw_table_header(pdf, xs, y, header_height, invoice_data.project_ref)
    y -= header_height

    for item in invoice_data.line_items:
        item_lines = _wrap_text(item.name, "Helvetica", 10, column_widths[0] - 4 * mm)
        item_height = max(row_height, (len(item_lines) * 4.6 + 4.2) * mm)
        _draw_table_row(
            pdf,
            xs,
            y,
            item_height,
            [item_lines, [item.quantity], [f"{item.unit_price} €"], [f"{item.amount} €"]],
            font_name="Helvetica",
            font_size=10,
        )
        y -= item_height

    summary_rows = [
        ("Summe", invoice_data.subtotal),
        (f"{invoice_data.vat_rate} % MwSt.", invoice_data.vat_amount),
        ("Gesamtbetrag", invoice_data.total),
    ]
    for label, amount in summary_rows:
        _draw_table_row(
            pdf,
            xs,
            y,
            summary_height,
            [[label], [""], [""], [f"{amount} €"]],
            font_name="Helvetica",
            font_size=10,
        )
        y -= summary_height

    if y < 54 * mm:
        raise ValueError("Invoice line items and totals do not fit above the footer.")

    return y


def _draw_table_header(
    pdf: canvas.Canvas,
    xs: list[float],
    y: float,
    height: float,
    project_ref: str | None,
) -> None:
    pdf.setLineWidth(1)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(xs[0] + 2 * mm, y - 7 * mm, _prefixed("Beauftragung: ", project_ref) or "Beauftragung:")
    pdf.line(xs[0], y - height, xs[1], y - height)

    headers = ["Menge", "Preis", "Summe"]
    for index, header in enumerate(headers, start=1):
        pdf.setFillGray(0.70)
        pdf.rect(xs[index], y - height, xs[index + 1] - xs[index], height, stroke=0, fill=1)
        pdf.setFillGray(0)
        pdf.rect(xs[index], y - height, xs[index + 1] - xs[index], height, stroke=1, fill=0)
        pdf.drawString(xs[index] + 2 * mm, y - 7 * mm, header)


def _draw_table_row(
    pdf: canvas.Canvas,
    xs: list[float],
    y: float,
    height: float,
    columns: list[list[str]],
    *,
    font_name: str,
    font_size: int,
) -> None:
    pdf.setLineWidth(1)
    for index, lines in enumerate(columns):
        pdf.rect(xs[index], y - height, xs[index + 1] - xs[index], height, stroke=1, fill=0)
        pdf.setFont(font_name, font_size)
        text_y = y - 6.2 * mm
        for line in lines:
            if line:
                pdf.drawString(xs[index] + 2 * mm, text_y, line)
            text_y -= 4.6 * mm


def _draw_notes(pdf: canvas.Canvas, table_bottom: float, invoice_data: InvoiceData) -> float:
    y = table_bottom - 14 * mm
    left = 25 * mm
    max_width = 160 * mm
    pdf.setFont("Helvetica", 10)
    for note in _present([invoice_data.cost_note, invoice_data.vat_note]):
        y = _draw_wrapped_lines(pdf, note, left, y, max_width, "Helvetica", 10, 5 * mm)
        y -= 3 * mm
    if invoice_data.due_date:
        payment_note = (
            f"Zahlbar bis {invoice_data.due_date} ohne Abzug auf unser unten angegebenes Konto. "
            "Bitte beachten Sie unsere neue Bankverbindung."
        )
        y = _draw_wrapped_lines(pdf, payment_note, left, y, max_width, "Helvetica", 10, 5 * mm)
        y -= 7 * mm
    pdf.drawString(left, y, "Wir bedanken uns für das entgegen gebrachte Vertrauen.")
    return y


def _draw_footer(pdf: canvas.Canvas, config: CollmexConfig) -> None:
    left = 25 * mm
    bottom = 9 * mm
    height = 20 * mm
    column_widths = [33.11 * mm, 39.51 * mm, 44.98 * mm, 45.68 * mm]
    xs = [left]
    for column_width in column_widths:
        xs.append(xs[-1] + column_width)

    columns = [
        [
            config.seller_name,
            config.seller_street,
            f"{config.seller_zip} {config.seller_city}",
            _display_seller_country(config.seller_country),
        ],
        _present(
            [
                _prefixed("phone: ", config.seller_phone),
                _prefixed("fax: ", config.seller_fax),
                config.seller_email,
                config.seller_web,
            ]
        ),
        _present(
            [
                "Geschäftsführung:",
                config.seller_geschaeftsfuehrung,
                config.seller_amtsgericht,
                _prefixed("HRB ", config.seller_hrb),
                _prefixed("Ust-ID: ", config.seller_vat_id),
            ]
        ),
        _present(
            [
                _prefixed("Bankverbindung: ", config.seller_bank_name),
                "IBAN:",
                config.seller_iban,
                _prefixed("BIC-Code: ", config.seller_bic),
            ]
        ),
    ]

    pdf.setLineWidth(0.5)
    for index, lines in enumerate(columns):
        pdf.rect(xs[index], bottom, xs[index + 1] - xs[index], height, stroke=1, fill=0)
        text_y = bottom + height - 4.2 * mm
        for line_index, line in enumerate(lines):
            font_name = "Helvetica-Bold" if line_index == 0 else "Helvetica"
            pdf.setFont(font_name, 7.5)
            wrapped = _wrap_text(line, font_name, 7.5, xs[index + 1] - xs[index] - 5 * mm)
            for wrapped_line in wrapped:
                pdf.drawString(xs[index] + 2 * mm, text_y, wrapped_line)
                text_y -= 3.3 * mm


def _present(lines: list[str | None]) -> list[str]:
    return [line for line in lines if line]


def _prefixed(prefix: str, value: str | None) -> str | None:
    if not value:
        return None
    return f"{prefix}{value}"


def _display_customer_country(country: str | None) -> str | None:
    if country == "DE":
        return "Deutschland"
    return country


def _display_seller_country(country: str | None) -> str | None:
    if country == "DE":
        return "Germany"
    return country


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_wrapped_lines(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str,
    font_size: float,
    line_height: float,
) -> float:
    pdf.setFont(font_name, font_size)
    for line in _wrap_text(text, font_name, font_size, max_width):
        pdf.drawString(x, y, line)
        y -= line_height
    return y
