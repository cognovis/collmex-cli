"""ReportLab renderer for customer invoice PDFs."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
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
    """Structured data needed to render a customer invoice."""

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
    template_path: Path | None = None,
) -> bytes:
    """Render a customer invoice PDF, optionally using an external template module."""
    seller_config = config or get_config()
    validate_seller_config(seller_config)

    if template_path is not None:
        pdf_bytes = _render_template_pdf(template_path, invoice_data, seller_config, logo_path)
    else:
        pdf_bytes = _render_generic_reportlab_pdf(invoice_data, seller_config)

    if output_path is not None:
        output_path.write_bytes(pdf_bytes)
    return pdf_bytes


def _render_template_pdf(
    template_path: Path,
    invoice_data: InvoiceData,
    config: CollmexConfig,
    logo_path: Path | None,
) -> bytes:
    resolved_template_path = template_path.expanduser().resolve()
    if not resolved_template_path.exists():
        raise FileNotFoundError(f"Invoice template not found: {resolved_template_path}")

    spec = importlib.util.spec_from_file_location("collmex_invoice_template", resolved_template_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load invoice template: {resolved_template_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    render = getattr(module, "render_invoice_pdf", None)
    if not callable(render):
        raise ValueError(
            f"Invoice template {resolved_template_path} must define "
            "render_invoice_pdf(invoice_data, config, logo_path=None)."
        )

    pdf_bytes = render(invoice_data, config, logo_path=logo_path)
    if not isinstance(pdf_bytes, bytes):
        raise TypeError(f"Invoice template {resolved_template_path} returned {type(pdf_bytes).__name__}, expected bytes.")
    return pdf_bytes


def _render_generic_reportlab_pdf(invoice_data: InvoiceData, config: CollmexConfig) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    width, height = A4

    _draw_generic_header(pdf, width, height, config, invoice_data)
    table_bottom = _draw_generic_line_items(pdf, width, height, invoice_data)
    _draw_generic_notes(pdf, table_bottom, invoice_data)
    _draw_generic_footer(pdf, width, config)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _draw_generic_header(
    pdf: canvas.Canvas,
    width: float,
    height: float,
    config: CollmexConfig,
    invoice_data: InvoiceData,
) -> None:
    left = 25 * mm
    right = width - 25 * mm
    y = height - 25 * mm

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(left, y, config.seller_name)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawRightString(right, y, "Rechnung")

    pdf.setFont("Helvetica", 9)
    for line in _present(
        [
            config.seller_street,
            f"{config.seller_zip} {config.seller_city}",
            config.seller_country,
            config.seller_email,
            config.seller_web,
        ]
    ):
        y -= 4 * mm
        pdf.drawString(left, y, line)

    recipient_y = height - 67 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, recipient_y, "Empfänger")
    recipient_y -= 6 * mm
    pdf.setFont("Helvetica", 10)
    for line in _present(
        [
            invoice_data.company_name,
            invoice_data.company_contact_name,
            invoice_data.address_line1,
            f"{invoice_data.postal_code} {invoice_data.city}",
            invoice_data.country,
            _prefixed("USt-IdNr.: ", invoice_data.vat_number),
        ]
    ):
        pdf.drawString(left, recipient_y, line)
        recipient_y -= 5 * mm

    meta_y = height - 67 * mm
    meta_x = width - 78 * mm
    pdf.setFont("Helvetica", 10)
    for line in _present(
        [
            f"Rechnungs-Nr.: {invoice_data.invoice_nr}",
            f"Datum: {invoice_data.invoice_date}",
            _prefixed("Lieferdatum: ", invoice_data.delivery_date),
            _prefixed("Beauftragung: ", invoice_data.project_ref),
        ]
    ):
        pdf.drawString(meta_x, meta_y, line)
        meta_y -= 5 * mm


def _draw_generic_line_items(pdf: canvas.Canvas, width: float, height: float, invoice_data: InvoiceData) -> float:
    if len(invoice_data.line_items) > 12:
        raise ValueError(
            f"Invoice has {len(invoice_data.line_items)} line items but the generic single-page renderer "
            "supports at most 12. Provide a custom template or split the invoice."
        )

    left = 25 * mm
    right = width - 25 * mm
    y = height - 122 * mm
    description_x = left
    quantity_x = width - 86 * mm
    price_x = width - 54 * mm
    amount_x = right

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(description_x, y, "Position")
    pdf.drawRightString(quantity_x, y, "Menge")
    pdf.drawRightString(price_x, y, "Preis")
    pdf.drawRightString(amount_x, y, "Summe")
    y -= 2 * mm
    pdf.line(left, y, right, y)
    y -= 6 * mm

    pdf.setFont("Helvetica", 9)
    for item in invoice_data.line_items:
        lines = _wrap_text(item.name, "Helvetica", 9, quantity_x - description_x - 7 * mm)
        row_height = max(7 * mm, len(lines) * 4.5 * mm)
        text_y = y
        for line in lines:
            pdf.drawString(description_x, text_y, line)
            text_y -= 4.5 * mm
        pdf.drawRightString(quantity_x, y, item.quantity)
        pdf.drawRightString(price_x, y, f"{item.unit_price} EUR")
        pdf.drawRightString(amount_x, y, f"{item.amount} EUR")
        y -= row_height

    y -= 4 * mm
    pdf.line(width - 95 * mm, y, right, y)
    y -= 6 * mm
    _draw_generic_total_row(pdf, width, y, "Zwischensumme:", f"{invoice_data.subtotal} EUR", bold=False)
    y -= 6 * mm
    _draw_generic_total_row(pdf, width, y, f"{invoice_data.vat_rate} % MwSt.:", f"{invoice_data.vat_amount} EUR", bold=False)
    y -= 7 * mm
    _draw_generic_total_row(pdf, width, y, "Gesamtbetrag:", f"{invoice_data.total} EUR", bold=True)
    return y


def _draw_generic_total_row(pdf: canvas.Canvas, width: float, y: float, label: str, amount: str, *, bold: bool) -> None:
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
    pdf.drawRightString(width - 55 * mm, y, label)
    pdf.drawRightString(width - 25 * mm, y, amount)


def _draw_generic_notes(pdf: canvas.Canvas, table_bottom: float, invoice_data: InvoiceData) -> None:
    y = table_bottom - 18 * mm
    left = 25 * mm
    max_width = 160 * mm
    pdf.setFont("Helvetica", 9)
    for note in _present([invoice_data.cost_note, invoice_data.vat_note]):
        y = _draw_wrapped_lines(pdf, note, left, y, max_width, "Helvetica", 9, 5 * mm)
        y -= 2 * mm
    if invoice_data.due_date:
        y = _draw_wrapped_lines(
            pdf,
            f"Zahlbar bis {invoice_data.due_date} ohne Abzug.",
            left,
            y,
            max_width,
            "Helvetica",
            9,
            5 * mm,
        )
        y -= 4 * mm
    pdf.drawString(left, y, "Vielen Dank.")


def _draw_generic_footer(pdf: canvas.Canvas, width: float, config: CollmexConfig) -> None:
    left = 25 * mm
    right = width - 25 * mm
    y = 22 * mm
    pdf.setFont("Helvetica", 7)
    footer_parts = _present(
        [
            _prefixed("Geschäftsführung: ", config.seller_geschaeftsfuehrung),
            config.seller_amtsgericht,
            _prefixed("HRB ", config.seller_hrb),
            _prefixed("USt-ID: ", config.seller_vat_id),
            _prefixed("Bank: ", config.seller_bank_name),
            _prefixed("IBAN: ", config.seller_iban),
            _prefixed("BIC: ", config.seller_bic),
        ]
    )
    pdf.line(left, y + 5 * mm, right, y + 5 * mm)
    _draw_wrapped_lines(pdf, " | ".join(footer_parts), left, y, right - left, "Helvetica", 7, 3.5 * mm)


def _present(lines: list[str | None]) -> list[str]:
    return [line for line in lines if line]


def _prefixed(prefix: str, value: str | None) -> str | None:
    if not value:
        return None
    return f"{prefix}{value}"


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
