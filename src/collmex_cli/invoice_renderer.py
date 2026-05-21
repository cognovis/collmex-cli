"""ReportLab renderer for cognovis customer invoice PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
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
            f"Set COLLMEX_SELLER_NAME, COLLMEX_SELLER_STREET, etc."
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
    _draw_recipient_and_metadata(pdf, width, height, invoice_data)
    table_bottom = _draw_line_items(pdf, height, invoice_data)
    notes_bottom = _draw_summary_and_notes(pdf, width, table_bottom, invoice_data)
    _draw_footer(pdf, width, config, notes_bottom)

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

    y = height - 42 * mm
    seller_lines = [
        config.seller_name,
        config.seller_street,
        f"{config.seller_zip} {config.seller_city}",
        config.seller_country,
        _prefixed("phone: ", config.seller_phone),
        _prefixed("fax: ", config.seller_fax),
        config.seller_email,
        config.seller_web,
    ]
    pdf.setFont("Helvetica", 8)
    for line in _present(seller_lines):
        pdf.drawRightString(width - 25 * mm, y, line)
        y -= 4 * mm

    pdf.setLineWidth(0.5)
    pdf.line(25 * mm, height - 78 * mm, width - 25 * mm, height - 78 * mm)


def _draw_recipient_and_metadata(pdf: canvas.Canvas, width: float, height: float, invoice_data: InvoiceData) -> None:
    recipient_y = height - 95 * mm
    recipient_lines = [
        invoice_data.company_name,
        invoice_data.company_contact_name,
        invoice_data.address_line1,
        f"{invoice_data.postal_code} {invoice_data.city}",
        invoice_data.country,
        _prefixed("USt-IdNr.: ", invoice_data.vat_number),
    ]

    pdf.setFont("Helvetica", 10)
    for line in _present(recipient_lines):
        pdf.drawString(25 * mm, recipient_y, line)
        recipient_y -= 5 * mm

    metadata_x = width - 70 * mm
    metadata_y = height - 95 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(metadata_x, metadata_y, f"Datum: {invoice_data.invoice_date}")
    metadata_y -= 12 * mm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(metadata_x, metadata_y, "Rechnung")
    metadata_y -= 8 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(metadata_x, metadata_y, f"Rechnungs-Nr.: {invoice_data.invoice_nr}")
    metadata_y -= 5 * mm
    if invoice_data.delivery_date:
        pdf.drawString(metadata_x, metadata_y, f"Lieferdatum: {invoice_data.delivery_date}")
        metadata_y -= 5 * mm
    if invoice_data.project_ref:
        pdf.drawString(metadata_x, metadata_y, f"Beauftragung: {invoice_data.project_ref}")


def _draw_line_items(pdf: canvas.Canvas, height: float, invoice_data: InvoiceData) -> float:
    max_items = 15
    if len(invoice_data.line_items) > max_items:
        raise ValueError(
            f"Invoice has {len(invoice_data.line_items)} line items but single-page renderer "
            f"supports at most {max_items}. Split into multiple invoices."
        )

    left = 25 * mm
    right = 185 * mm
    y = height - 155 * mm
    quantity_x = 118 * mm
    price_x = 150 * mm
    amount_x = right

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left, y, "Bezeichnung")
    pdf.drawRightString(quantity_x, y, "Menge")
    pdf.drawRightString(price_x, y, "Preis")
    pdf.drawRightString(amount_x, y, "Summe")
    y -= 2 * mm
    pdf.line(left, y, right, y)
    y -= 6 * mm

    pdf.setFont("Helvetica", 9)
    for item in invoice_data.line_items:
        pdf.drawString(left, y, item.name)
        pdf.drawRightString(quantity_x, y, item.quantity)
        pdf.drawRightString(price_x, y, f"{item.unit_price} EUR")
        pdf.drawRightString(amount_x, y, f"{item.amount} EUR")
        y -= 7 * mm

    return y


def _draw_summary_and_notes(pdf: canvas.Canvas, width: float, y: float, invoice_data: InvoiceData) -> float:
    label_x = width - 75 * mm
    amount_x = width - 25 * mm
    y -= 5 * mm

    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(label_x, y, "Zwischensumme:")
    pdf.drawRightString(amount_x, y, f"{invoice_data.subtotal} EUR")
    y -= 6 * mm
    pdf.drawRightString(label_x, y, f"{invoice_data.vat_rate} % MwSt.:")
    pdf.drawRightString(amount_x, y, f"{invoice_data.vat_amount} EUR")
    y -= 7 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(label_x, y, "Gesamtbetrag:")
    pdf.drawRightString(amount_x, y, f"{invoice_data.total} EUR")

    y -= 18 * mm
    pdf.setFont("Helvetica", 9)
    for note in _present([invoice_data.cost_note, invoice_data.vat_note]):
        pdf.drawString(25 * mm, y, note)
        y -= 5 * mm
    if invoice_data.due_date:
        pdf.drawString(25 * mm, y, f"Zahlbar bis {invoice_data.due_date} ohne Abzug auf unser unten angegebenes Konto.")
        y -= 5 * mm
    pdf.drawString(25 * mm, y, "Wir bedanken uns für das entgegengebrachte Vertrauen.")
    return y


def _draw_footer(pdf: canvas.Canvas, width: float, config: CollmexConfig, notes_bottom: float) -> None:
    footer_y = min(38 * mm, max(25 * mm, notes_bottom - 20 * mm))
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(
        width / 2,
        footer_y + 7 * mm,
        f"{config.seller_name} - project management solutions - "
        f"{config.seller_street} - {config.seller_zip} {config.seller_city}",
    )
    legal_parts = [
        _prefixed("Geschäftsführung: ", config.seller_geschaeftsfuehrung),
        config.seller_amtsgericht,
        _prefixed("HRB ", config.seller_hrb),
        _prefixed("Ust-ID: ", config.seller_vat_id),
        _prefixed("Bankverbindung: ", config.seller_bank_name),
        _prefixed("IBAN: ", config.seller_iban),
        _prefixed("BIC-Code: ", config.seller_bic),
    ]
    pdf.drawCentredString(width / 2, footer_y, " | ".join(_present(legal_parts)))


def _present(lines: list[str | None]) -> list[str]:
    return [line for line in lines if line]


def _prefixed(prefix: str, value: str | None) -> str | None:
    if not value:
        return None
    return f"{prefix}{value}"
