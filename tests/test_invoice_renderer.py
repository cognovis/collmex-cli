"""Tests for the cognovis invoice PDF renderer."""

from io import BytesIO

import pytest
from pypdf import PdfReader

from collmex_cli.config import CollmexConfig
from collmex_cli.invoice_renderer import (
    InvoiceData,
    InvoiceLineItem,
    render_invoice_pdf,
    validate_seller_config,
)


def _seller_config(**overrides: str | None) -> CollmexConfig:
    values = {
        "customer_id": "123456",
        "seller_name": "cognovis GmbH",
        "seller_street": "Schroedersweg 27",
        "seller_zip": "22453",
        "seller_city": "Hamburg",
        "seller_country": "Germany",
        "seller_phone": "+49 (40) 386 60 521",
        "seller_fax": "+49 (40) 386 60 523",
        "seller_web": "http://www.cognovis.de",
        "seller_email": "info@cognovis.de",
        "seller_vat_id": "DE118620281",
        "seller_hrb": "28909",
        "seller_amtsgericht": "Amtsgericht Hamburg",
        "seller_geschaeftsfuehrung": "Malte Sussdorff",
        "seller_bank_name": "Fyrst",
        "seller_iban": "DE93200704040062444500",
        "seller_bic": "DEUTDEHHXXX",
    }
    values.update(overrides)
    return CollmexConfig(**values)


def _invoice_data() -> InvoiceData:
    return InvoiceData(
        company_name="solutio GmbH",
        company_contact_name="Max Mustermann",
        address_line1="Musterstrasse 1",
        postal_code="20095",
        city="Hamburg",
        country="Germany",
        vat_number="DE123456789",
        invoice_nr="I2026_04_0001",
        invoice_date="21.05.2026",
        delivery_date="30.04.2026",
        project_ref="PO-2026-04",
        line_items=[
            InvoiceLineItem("Beratung", "10,00 Std.", "185,00", "1.850,00"),
            InvoiceLineItem("Reisekosten", "1 Stk.", "150,00", "150,00"),
        ],
        subtotal="14.064,63",
        vat_rate="19",
        vat_amount="2.672,28",
        total="16.736,91",
        cost_note="Reisekosten gemäß Vereinbarung.",
        vat_note="Leistungsort Deutschland.",
        due_date="20.06.2026",
    )


def test_renders_pdf(tmp_path):
    """Structured invoice data renders a one-page PDF and writes it when requested."""
    output_path = tmp_path / "invoice.pdf"

    pdf_bytes = render_invoice_pdf(_invoice_data(), config=_seller_config(), output_path=output_path)

    assert pdf_bytes.startswith(b"%PDF")
    assert output_path.read_bytes() == pdf_bytes
    assert b"/Count 1" in pdf_bytes


def test_layout_contains_template_sections():
    """PDF contains the key sections from RechnungCognovis.de.fodt."""
    pdf_bytes = render_invoice_pdf(_invoice_data(), config=_seller_config())

    for expected in [
        b"cognovis GmbH",
        b"solutio GmbH",
        b"Rechnung",
        b"I2026_04_0001",
        b"Lieferdatum",
        b"Beauftragung",
        b"Menge",
        b"Preis",
        b"Summe",
        b"Gesamtbetrag",
    ]:
        assert expected in pdf_bytes


def test_footer_pflichtangaben():
    """Footer includes the mandatory legal and bank details from seller config."""
    pdf_bytes = render_invoice_pdf(_invoice_data(), config=_seller_config())
    visible_text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf_bytes)).pages)

    for expected in [
        b"Schroedersweg 27",
        b"22453 Hamburg",
        b"DE118620281",
        b"HRB 28909",
        b"Amtsgericht Hamburg",
        b"Malte",
        b"Sussdorff",
        b"DE93200704040062444500",
        b"DEUTDEHHXXX",
    ]:
        assert expected in pdf_bytes
    assert b"Gesch" in pdf_bytes
    assert b"ftsf" in pdf_bytes
    assert b"Geschaeftsfuehrung" not in pdf_bytes
    assert "Geschäftsführung:\nMalte Sussdorff" in visible_text


def test_notes_use_german_umlauts():
    """Customer-facing German note text uses proper umlauts."""
    pdf_bytes = render_invoice_pdf(_invoice_data(), config=_seller_config())

    assert b"Wir bedanken uns f" in pdf_bytes
    assert b"fuer" not in pdf_bytes
    assert b"gemaess" not in pdf_bytes


def test_multiline_totals():
    """Multi-position invoice renders columns and the reference invoice totals."""
    pdf_bytes = render_invoice_pdf(_invoice_data(), config=_seller_config())

    for expected in [
        b"Beratung",
        b"10,00 Std.",
        b"185,00",
        b"1.850,00",
        b"Reisekosten",
        b"1 Stk.",
        b"150,00",
        b"14.064,63",
        b"2.672,28",
        b"16.736,91",
    ]:
        assert expected in pdf_bytes


def test_layout_uses_tabular_footer_and_invoice_title():
    """Invoice layout follows the compact tabular cognovis template."""
    pdf_bytes = render_invoice_pdf(_invoice_data(), config=_seller_config())

    assert b"Rechnung I2026_04_0001" in pdf_bytes
    assert b"Bankverbindung: Fyrst" in pdf_bytes
    assert b"Zahlbar bis 20.06.2026" in pdf_bytes
    assert b"Rechnungs-Nr." not in pdf_bytes


def test_validate_seller_config_reports_missing_fields():
    """Missing mandatory seller config fields raise a clear error."""
    with pytest.raises(ValueError, match="seller_street"):
        validate_seller_config(_seller_config(seller_street=None))


def test_rejects_too_many_line_items_for_single_page_renderer():
    """Invoices that cannot fit the one-page renderer fail clearly."""
    invoice = _invoice_data()
    invoice.line_items = [
        InvoiceLineItem(f"Beratung {index}", "1,00 Std.", "185,00", "185,00") for index in range(9)
    ]

    with pytest.raises(ValueError, match="supports at most 8"):
        render_invoice_pdf(invoice, config=_seller_config())
