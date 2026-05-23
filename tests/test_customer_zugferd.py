"""Tests for customer-facing ZUGFeRD PDF invoice generation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
import json
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
from facturx import xml_check_schematron
import pikepdf
from pikepdf import Name
from pypdf import PdfReader
from typer.testing import CliRunner

from collmex_cli.config import CollmexConfig
from collmex_cli.invoice_renderer import InvoiceData, InvoiceLineItem, render_invoice_pdf
from collmex_cli.main import app
from collmex_cli.models import Customer
from collmex_cli.zugferd import (
    create_customer_zugferd_xml,
    embed_xml_in_pdf,
    validate_customer_for_zugferd,
)


runner = CliRunner()


def _seller_config(**overrides: str | None) -> CollmexConfig:
    values = {
        "customer_id": "123456",
        "seller_name": "cognovis GmbH",
        "seller_street": "Schroedersweg 27",
        "seller_zip": "22453",
        "seller_city": "Hamburg",
        "seller_country": "DE",
        "seller_phone": "+49 (40) 386 60 521",
        "seller_fax": "+49 (40) 386 60 523",
        "seller_web": "https://www.cognovis.de",
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


def _customer(**overrides: str) -> Customer:
    values = {
        "customer_id": 42,
        "company_name": "solutio GmbH",
        "street": "Kundenstrasse 1",
        "zip_code": "20095",
        "city": "Hamburg",
        "country": "DE",
        "email": "rechnung@example.com",
        "vat_id": "DE123456789",
    }
    values.update(overrides)
    return Customer(**values)


def _line_items() -> list[dict[str, Decimal | str]]:
    return [
        {
            "description": "Beratung",
            "quantity": Decimal("10.00"),
            "unit_price": Decimal("185.00"),
            "tax_rate": Decimal("19.00"),
            "unit": "HUR",
        },
        {
            "description": "Reisekosten",
            "quantity": Decimal("1.00"),
            "unit_price": Decimal("150.00"),
            "tax_rate": Decimal("19.00"),
            "unit": "C62",
        },
    ]


def _invoice_data() -> InvoiceData:
    return InvoiceData(
        company_name="solutio GmbH",
        company_contact_name=None,
        address_line1="Kundenstrasse 1",
        postal_code="20095",
        city="Hamburg",
        country="DE",
        vat_number="DE123456789",
        invoice_nr="I2026_05_0001",
        invoice_date="21.05.2026",
        delivery_date="21.05.2026",
        project_ref=None,
        line_items=[
            InvoiceLineItem("Beratung", "10.00 HUR", "185.00", "1850.00"),
            InvoiceLineItem("Reisekosten", "1.00 C62", "150.00", "150.00"),
        ],
        subtotal="2000.00",
        vat_rate="19.00",
        vat_amount="380.00",
        total="2380.00",
    )


def _xml_text(xml_bytes: bytes) -> str:
    return xml_bytes.decode("utf-8")


def _xml_root(xml_bytes: bytes) -> ET.Element:
    return ET.fromstring(xml_bytes)


def _embedded_facturx_xml(pdf_bytes: bytes) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    attachments = reader.attachments
    assert "factur-x.xml" in attachments
    attachment = attachments["factur-x.xml"]
    if isinstance(attachment, list):
        return attachment[0]
    return attachment


def _zugferd_pdf_bytes() -> bytes:
    xml_bytes = create_customer_zugferd_xml(
        customer=_customer(),
        invoice_number="I2026_05_0001",
        invoice_date=date(2026, 5, 21),
        line_items=_line_items(),
        config=_seller_config(),
    )
    pdf_bytes = render_invoice_pdf(
        invoice_data=_invoice_data(),
        config=_seller_config(),
    )
    return embed_xml_in_pdf(pdf_bytes, xml_bytes)


def test_seller_buyer_roles(tmp_path):
    """CLI output embeds XML with cognovis as seller and the Collmex customer as buyer."""
    customer = _customer()
    output_path = tmp_path / "invoice.pdf"
    items = [
        {"desc": "Beratung", "qty": "1", "unit_price": "100.00", "tax_rate": "19", "unit": "HUR"}
    ]
    env = {
        "COLLMEX_CUSTOMER_ID": "123456",
        "COLLMEX_SELLER_NAME": "cognovis GmbH",
        "COLLMEX_SELLER_STREET": "Schroedersweg 27",
        "COLLMEX_SELLER_ZIP": "22453",
        "COLLMEX_SELLER_CITY": "Hamburg",
        "COLLMEX_SELLER_COUNTRY": "DE",
        "COLLMEX_SELLER_EMAIL": "info@cognovis.de",
        "COLLMEX_SELLER_VAT_ID": "DE118620281",
        "COLLMEX_SELLER_HRB": "28909",
        "COLLMEX_SELLER_AMTSGERICHT": "Amtsgericht Hamburg",
        "COLLMEX_SELLER_GESCHAEFTSFUEHRUNG": "Malte Sussdorff",
        "COLLMEX_SELLER_BANK_NAME": "Fyrst",
        "COLLMEX_SELLER_IBAN": "DE93200704040062444500",
        "COLLMEX_SELLER_BIC": "DEUTDEHHXXX",
    }

    with patch("collmex_cli.main.CollmexClient", autospec=True) as mock_client_cls:
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_customers.return_value = [customer]
        result = runner.invoke(
            app,
            [
                "customer-zugferd-create",
                "--customer-id",
                "42",
                "--invoice",
                "I2026_05_0001",
                "--date",
                "2026-05-21",
                "--items",
                json.dumps(items),
                "--output",
                str(output_path),
            ],
            env=env,
        )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    sidecar_xml_path = output_path.with_suffix(".xml")
    assert sidecar_xml_path.exists()
    xml = _xml_text(_embedded_facturx_xml(output_path.read_bytes()))
    assert sidecar_xml_path.read_bytes() == _embedded_facturx_xml(output_path.read_bytes())
    assert "<ram:SellerTradeParty>" in xml
    assert "cognovis GmbH" in xml
    assert "DE118620281" in xml
    assert "<ram:BuyerTradeParty>" in xml
    assert "solutio GmbH" in xml
    assert "Kundenstrasse 1" in xml
    instance.get_customers.assert_called_once_with(customer_id=42)


def test_xml_validates_en16931():
    """Customer ZUGFeRD XML passes EN16931 schema and schematron validation."""
    xml_bytes = create_customer_zugferd_xml(
        customer=_customer(),
        invoice_number="I2026_05_0001",
        invoice_date=date(2026, 5, 21),
        line_items=_line_items(),
        config=_seller_config(),
    )

    root = _xml_root(xml_bytes)
    assert root.tag.endswith("CrossIndustryInvoice")
    assert "urn:cen.eu:en16931:2017" in _xml_text(xml_bytes)
    assert xml_check_schematron(xml_bytes, flavor="factur-x", level="en16931") is True


def test_output_pdfa3_embedded_xml():
    """PDF output contains the cognovis invoice layout and an embedded Factur-X XML file."""
    xml_bytes = create_customer_zugferd_xml(
        customer=_customer(),
        invoice_number="I2026_05_0001",
        invoice_date=date(2026, 5, 21),
        line_items=_line_items(),
        config=_seller_config(),
    )
    pdf_bytes = render_invoice_pdf(
        invoice_data=_invoice_data(),
        config=_seller_config(),
    )

    output_bytes = embed_xml_in_pdf(pdf_bytes, xml_bytes)

    assert output_bytes.startswith(b"%PDF")
    assert b"cognovis GmbH" in output_bytes
    assert _embedded_facturx_xml(output_bytes) == xml_bytes


def test_output_pdf_contains_pdfa3b_xmp_metadata():
    """PDF output declares PDF/A-3B conformance in XMP metadata."""
    output_bytes = _zugferd_pdf_bytes()

    with pikepdf.open(BytesIO(output_bytes)) as pdf:
        with pdf.open_metadata() as metadata:
            assert metadata["pdfaid:part"] == "3"
            assert metadata["pdfaid:conformance"] == "B"


def test_output_pdf_contains_output_intent_with_valid_icc_profile():
    """PDF output contains an OutputIntent with an embedded RGB ICC profile."""
    output_bytes = _zugferd_pdf_bytes()

    with pikepdf.open(BytesIO(output_bytes)) as pdf:
        output_intents = pdf.Root["/OutputIntents"]
        assert len(output_intents) >= 1
        output_intent = output_intents[0]
        assert output_intent["/Type"] == Name("/OutputIntent")
        assert output_intent["/S"] == Name("/GTS_PDFA1")
        assert output_intent["/OutputConditionIdentifier"] == "sRGB IEC61966-2.1"

        icc_profile = output_intent["/DestOutputProfile"]
        icc_bytes = icc_profile.read_bytes()
        assert icc_profile["/N"] == 3
        assert int.from_bytes(icc_bytes[:4], byteorder="big") == len(icc_bytes)
        assert icc_bytes[36:40] == b"acsp"


def test_pdfa3b_conformance_confirmed_by_pikepdf_inspection():
    """pikepdf inspection confirms the PDF/A-3B markers needed by validators."""
    output_bytes = _zugferd_pdf_bytes()

    with pikepdf.open(BytesIO(output_bytes)) as pdf:
        with pdf.open_metadata() as metadata:
            assert metadata["pdfaid:part"] == "3"
            assert metadata["pdfaid:conformance"] == "B"
        assert pdf.Root["/OutputIntents"][0]["/DestOutputProfile"].read_bytes()[36:40] == b"acsp"


def test_multiline_invoice_totals():
    """Multiple hour and travel-cost lines generate complete net, VAT, and gross totals."""
    xml_bytes = create_customer_zugferd_xml(
        customer=_customer(),
        invoice_number="I2026_05_0001",
        invoice_date=date(2026, 5, 21),
        line_items=_line_items(),
        config=_seller_config(),
    )
    xml = _xml_text(xml_bytes)

    assert "Beratung" in xml
    assert "Reisekosten" in xml
    assert "<ram:LineTotalAmount>2000.00</ram:LineTotalAmount>" in xml
    assert "<ram:TaxBasisTotalAmount>2000.00</ram:TaxBasisTotalAmount>" in xml
    assert '<ram:TaxTotalAmount currencyID="EUR">380.00</ram:TaxTotalAmount>' in xml
    assert "<ram:GrandTotalAmount>2380.00</ram:GrandTotalAmount>" in xml


def test_missing_master_data_errors():
    """Missing seller or buyer master data fails with clear messages."""
    with pytest.raises(ValueError, match="seller_street"):
        create_customer_zugferd_xml(
            customer=_customer(),
            invoice_number="I2026_05_0001",
            invoice_date=date(2026, 5, 21),
            line_items=_line_items(),
            config=_seller_config(seller_street=None),
        )

    missing = validate_customer_for_zugferd(_customer(street=""))
    assert missing == ["street"]

    with pytest.raises(ValueError, match="Customer 42 is missing required field: street"):
        create_customer_zugferd_xml(
            customer=_customer(street=""),
            invoice_number="I2026_05_0001",
            invoice_date=date(2026, 5, 21),
            line_items=_line_items(),
            config=_seller_config(),
        )
