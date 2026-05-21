"""ZUGFeRD XML generation for vendor and customer invoices.

Uses python-drafthorse to generate EN 16931 compliant XML.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import tempfile

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem

from .config import CollmexConfig, get_config
from .invoice_renderer import InvoiceData, InvoiceLineItem, validate_seller_config
from .models import Customer, Vendor


def validate_vendor_for_zugferd(vendor: Vendor) -> list[str]:
    """Validate that a vendor has all required fields for ZUGFeRD XML generation.

    Checks: street, postal_code, city, and vat_id OR tax_id (at least one).

    Args:
        vendor: Vendor to validate

    Returns:
        List of missing field names (empty list if all required fields are present)
    """
    missing = []
    if not vendor.street:
        missing.append("street")
    if not vendor.postal_code:
        missing.append("postal_code")
    if not vendor.city:
        missing.append("city")
    if not vendor.vat_id and not vendor.tax_id:
        missing.append("vat_id")
    return missing


def validate_customer_for_zugferd(customer: Customer) -> list[str]:
    """Validate that a customer has all required buyer fields for ZUGFeRD."""
    missing = []
    if not (customer.company_name or f"{customer.first_name} {customer.last_name}".strip()):
        missing.append("name")
    if not customer.street:
        missing.append("street")
    if not customer.zip_code:
        missing.append("zip_code")
    if not customer.city:
        missing.append("city")
    return missing


def create_customer_zugferd_xml(
    customer: Customer,
    invoice_number: str,
    invoice_date: date,
    line_items: list[dict],
    config: CollmexConfig | None = None,
    delivery_date: date | None = None,
    payment_terms_text: str | None = None,
    due_date: date | None = None,
    notes: str | None = None,
) -> bytes:
    """Create EN 16931 ZUGFeRD XML for a cognovis customer invoice."""
    config = config or get_config()
    validate_seller_config(config)
    _raise_for_missing_customer_fields(customer)

    doc = Document()
    doc.context.guideline_parameter.id = "urn:cen.eu:en16931:2017"
    doc.header.id = invoice_number
    doc.header.type_code = "380"
    doc.header.issue_date_time = invoice_date
    doc.trade.delivery.event.occurrence = delivery_date or invoice_date

    if notes:
        note = IncludedNote()
        note.content = notes
        doc.header.notes.add(note)

    doc.trade.agreement.seller.name = config.seller_name
    doc.trade.agreement.seller.address.line_one = config.seller_street
    doc.trade.agreement.seller.address.postcode = config.seller_zip
    doc.trade.agreement.seller.address.city_name = config.seller_city
    doc.trade.agreement.seller.address.country_id = config.seller_country

    seller_tax_reg = TaxRegistration()
    seller_tax_reg.id = ("VA", config.seller_vat_id)
    doc.trade.agreement.seller.tax_registrations.add(seller_tax_reg)

    doc.trade.agreement.buyer.name = _customer_name(customer)
    if customer.customer_id is not None:
        doc.trade.agreement.buyer.id = str(customer.customer_id)
    doc.trade.agreement.buyer.address.line_one = customer.street
    doc.trade.agreement.buyer.address.postcode = customer.zip_code
    doc.trade.agreement.buyer.address.city_name = customer.city
    doc.trade.agreement.buyer.address.country_id = customer.country or "DE"

    if customer.vat_id:
        buyer_tax_reg = TaxRegistration()
        buyer_tax_reg.id = ("VA", customer.vat_id)
        doc.trade.agreement.buyer.tax_registrations.add(buyer_tax_reg)

    total_net, tax_amounts = _add_line_items(doc, line_items)

    doc.trade.settlement.currency_code = "EUR"

    pm = PaymentMeans()
    pm.type_code = "58"
    pm.payee_account.iban = config.seller_iban
    pm.payee_institution.bic = config.seller_bic
    doc.trade.settlement.payment_means.add(pm)

    due_date = due_date or invoice_date + timedelta(days=14)
    if not payment_terms_text:
        payment_terms_text = f"Zahlbar bis {due_date.strftime('%d.%m.%Y')}."
    terms = PaymentTerms()
    terms.description = payment_terms_text
    terms.due = due_date
    doc.trade.settlement.terms.add(terms)

    _add_settlement_totals(doc, total_net, tax_amounts)

    return doc.serialize(schema="FACTUR-X_EN16931")


def create_customer_invoice_data(
    customer: Customer,
    invoice_number: str,
    invoice_date: date,
    line_items: list[dict],
    *,
    delivery_date: date | None = None,
    project_ref: str | None = None,
    due_date: date | None = None,
    cost_note: str | None = None,
    vat_note: str | None = None,
) -> InvoiceData:
    """Build renderer input from customer and invoice line items."""
    _raise_for_missing_customer_fields(customer)
    totals = _calculate_totals(line_items)
    return InvoiceData(
        company_name=_customer_name(customer),
        company_contact_name=None,
        address_line1=customer.street,
        postal_code=customer.zip_code,
        city=customer.city,
        country=customer.country or "DE",
        vat_number=customer.vat_id or None,
        invoice_nr=invoice_number,
        invoice_date=_format_display_date(invoice_date),
        delivery_date=_format_display_date(delivery_date) if delivery_date else None,
        project_ref=project_ref,
        line_items=[
            InvoiceLineItem(
                name=str(item["description"]),
                quantity=f"{_money_decimal(item['quantity'])} {item.get('unit', 'C62')}",
                unit_price=_format_amount(_money_decimal(item["unit_price"])),
                amount=_format_amount(_money_decimal(item["quantity"]) * _money_decimal(item["unit_price"])),
            )
            for item in line_items
        ],
        subtotal=_format_amount(totals["net"]),
        vat_rate=_format_amount(totals["tax_rate"]),
        vat_amount=_format_amount(totals["tax"]),
        total=_format_amount(totals["gross"]),
        cost_note=cost_note,
        vat_note=vat_note,
        due_date=_format_display_date(due_date) if due_date else None,
    )


def embed_xml_in_pdf(pdf_content: bytes, xml_content: bytes, xml_filename: str = "factur-x.xml") -> bytes:
    """Embed Factur-X XML into a PDF, using factur-x when available."""
    try:
        import facturx
    except ImportError:
        return _embed_xml_with_pypdf(pdf_content, xml_content, xml_filename)

    generate_from_binary = getattr(facturx, "generate_from_binary", None)
    if generate_from_binary is not None:
        for kwargs in (
            {"facturx_level": "en16931", "check_xsd": False, "check_shematron": False},
            {"facturx_level": "en16931"},
            {},
        ):
            try:
                return generate_from_binary(pdf_content, xml_content, **kwargs)
            except TypeError:
                continue

    generate_from_file = getattr(facturx, "generate_from_file", None)
    if generate_from_file is not None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_path = tmp_path / "invoice.pdf"
            xml_path = tmp_path / xml_filename
            output_path = tmp_path / "zugferd.pdf"
            pdf_path.write_bytes(pdf_content)
            xml_path.write_bytes(xml_content)
            generate_from_file(pdf_path, xml_path, output_pdf_file=output_path)
            return output_path.read_bytes()

    return _embed_xml_with_pypdf(pdf_content, xml_content, xml_filename)


def _raise_for_missing_customer_fields(customer: Customer) -> None:
    missing = validate_customer_for_zugferd(customer)
    if missing:
        identifier = customer.customer_id if customer.customer_id is not None else _customer_name(customer) or "unknown"
        if len(missing) == 1:
            raise ValueError(f"Customer {identifier} is missing required field: {missing[0]}")
        raise ValueError(f"Customer {identifier} is missing required fields: {', '.join(missing)}")


def _customer_name(customer: Customer) -> str:
    return customer.company_name or f"{customer.first_name} {customer.last_name}".strip()


def _add_line_items(doc: Document, line_items: list[dict]) -> tuple[Decimal, dict[str, tuple[Decimal, Decimal]]]:
    total_net = Decimal("0.00")
    tax_amounts: dict[str, tuple[Decimal, Decimal]] = {}

    for i, item in enumerate(line_items, start=1):
        line = LineItem()
        line.document.line_id = str(i)
        line.product.name = str(item["description"])

        quantity = _money_decimal(item["quantity"])
        unit_price = _money_decimal(item["unit_price"])
        tax_rate = _money_decimal(item.get("tax_rate", "19.00"))
        unit = item.get("unit", "C62")

        line.agreement.net.amount = unit_price
        line.agreement.net.basis_quantity = (Decimal("1.000"), unit)
        line.delivery.billed_quantity = (quantity, unit)
        line.settlement.trade_tax.type_code = "VAT"
        line.settlement.trade_tax.category_code = "S"
        line.settlement.trade_tax.rate_applicable_percent = tax_rate

        line_total = (quantity * unit_price).quantize(Decimal("0.01"))
        line.settlement.monetary_summation.total_amount = line_total
        total_net += line_total

        rate_key = str(tax_rate)
        tax_amount = (line_total * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        if rate_key in tax_amounts:
            basis, tax = tax_amounts[rate_key]
            tax_amounts[rate_key] = (basis + line_total, tax + tax_amount)
        else:
            tax_amounts[rate_key] = (line_total, tax_amount)

        doc.trade.items.add(line)

    return total_net, tax_amounts


def _add_settlement_totals(
    doc: Document,
    total_net: Decimal,
    tax_amounts: dict[str, tuple[Decimal, Decimal]],
) -> None:
    total_tax = Decimal("0.00")
    for rate_str, (basis, tax) in tax_amounts.items():
        trade_tax = ApplicableTradeTax()
        trade_tax.calculated_amount = tax
        trade_tax.basis_amount = basis
        trade_tax.type_code = "VAT"
        trade_tax.category_code = "S"
        trade_tax.rate_applicable_percent = Decimal(rate_str)
        doc.trade.settlement.trade_tax.add(trade_tax)
        total_tax += tax

    total_net = total_net.quantize(Decimal("0.01"))
    total_tax = total_tax.quantize(Decimal("0.01"))
    gross_total = (total_net + total_tax).quantize(Decimal("0.01"))
    doc.trade.settlement.monetary_summation.line_total = total_net
    doc.trade.settlement.monetary_summation.charge_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.allowance_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.tax_basis_total = total_net
    doc.trade.settlement.monetary_summation.tax_total = (total_tax, "EUR")
    doc.trade.settlement.monetary_summation.grand_total = gross_total
    doc.trade.settlement.monetary_summation.prepaid_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.due_amount = gross_total


def _calculate_totals(line_items: list[dict]) -> dict[str, Decimal]:
    net = Decimal("0.00")
    tax = Decimal("0.00")
    tax_rate = Decimal("0.00")
    for item in line_items:
        line_net = _money_decimal(item["quantity"]) * _money_decimal(item["unit_price"])
        item_tax_rate = _money_decimal(item.get("tax_rate", "19.00"))
        net += line_net
        tax += line_net * item_tax_rate / Decimal("100")
        tax_rate = item_tax_rate
    return {"net": net, "tax": tax, "gross": net + tax, "tax_rate": tax_rate}


def _money_decimal(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _format_amount(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def _format_display_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _embed_xml_with_pypdf(pdf_content: bytes, xml_content: bytes, xml_filename: str) -> bytes:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(BytesIO(pdf_content))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_attachment(xml_filename, xml_content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def create_zugferd_xml(
    vendor: Vendor,
    invoice_number: str,
    invoice_date: date,
    line_items: list[dict],
    config: CollmexConfig | None = None,
    buyer_customer_id: str | None = None,
    payment_terms_text: str | None = None,
    due_date: date | None = None,
    notes: str | None = None,
) -> bytes:
    """Create a ZUGFeRD 2.x XML document for a vendor invoice.

    Args:
        vendor: The vendor (seller) information from Collmex
        invoice_number: Invoice number
        invoice_date: Invoice date
        line_items: List of line items, each dict with:
            - description: str
            - quantity: Decimal
            - unit: str (e.g., "C62" for pieces, "HUR" for hours)
            - unit_price: Decimal (net price)
            - tax_rate: Decimal (e.g., 19.00 or 7.00)
        config: Optional config, loads from env if not provided
        buyer_customer_id: Your customer ID at the vendor (optional)
        payment_terms_text: Payment terms description
        due_date: Payment due date
        notes: Additional notes for the invoice

    Returns:
        XML bytes in UN/CEFACT CII format (EN 16931)
    """
    config = config or get_config()

    if not config.buyer_configured:
        raise ValueError(
            "Buyer configuration missing. Set COLLMEX_BUYER_NAME, "
            "COLLMEX_BUYER_STREET, COLLMEX_BUYER_ZIP, COLLMEX_BUYER_CITY"
        )

    doc = Document()
    doc.context.guideline_parameter.id = "urn:cen.eu:en16931:2017"
    doc.header.id = invoice_number
    doc.header.type_code = "380"  # Commercial invoice
    doc.header.issue_date_time = invoice_date

    # Add notes if provided
    if notes:
        note = IncludedNote()
        note.content = notes
        doc.header.notes.add(note)

    # Seller (Vendor) party
    doc.trade.agreement.seller.name = vendor.company_name or f"{vendor.first_name} {vendor.last_name}".strip()

    if vendor.street:
        doc.trade.agreement.seller.address.line_one = vendor.street
    if vendor.postal_code:
        doc.trade.agreement.seller.address.postcode = vendor.postal_code
    if vendor.city:
        doc.trade.agreement.seller.address.city_name = vendor.city
    doc.trade.agreement.seller.address.country_id = vendor.country or "DE"

    if vendor.email:
        doc.trade.agreement.seller.electronic_address.uri_ID = (vendor.email, "EM")

    if vendor.vat_id:
        tax_reg = TaxRegistration()
        tax_reg.id = ("VA", vendor.vat_id)
        doc.trade.agreement.seller.tax_registrations.add(tax_reg)

    # Buyer (your company) party
    doc.trade.agreement.buyer.name = config.buyer_name

    if buyer_customer_id:
        doc.trade.agreement.buyer.id = buyer_customer_id

    if config.buyer_street:
        doc.trade.agreement.buyer.address.line_one = config.buyer_street
    if config.buyer_zip:
        doc.trade.agreement.buyer.address.postcode = config.buyer_zip
    if config.buyer_city:
        doc.trade.agreement.buyer.address.city_name = config.buyer_city
    doc.trade.agreement.buyer.address.country_id = config.buyer_country

    if config.buyer_email:
        doc.trade.agreement.buyer.electronic_address.uri_ID = (config.buyer_email, "EM")

    if config.buyer_vat_id:
        buyer_tax_reg = TaxRegistration()
        buyer_tax_reg.id = ("VA", config.buyer_vat_id)
        doc.trade.agreement.buyer.tax_registrations.add(buyer_tax_reg)

    # Line items
    total_net = Decimal("0.00")
    tax_amounts: dict[str, tuple[Decimal, Decimal]] = {}  # rate -> (basis, tax)

    for i, item in enumerate(line_items, start=1):
        line = LineItem()
        line.document.line_id = str(i)

        line.product.name = item["description"]

        quantity = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item["unit_price"]))
        tax_rate = Decimal(str(item.get("tax_rate", "19.00")))
        unit = item.get("unit", "C62")  # C62 = pieces

        line.agreement.net.amount = unit_price
        line.agreement.net.basis_quantity = (Decimal("1.000"), unit)

        line.delivery.billed_quantity = (quantity, unit)

        line.settlement.trade_tax.type_code = "VAT"
        line.settlement.trade_tax.category_code = "S"  # Standard rate
        line.settlement.trade_tax.rate_applicable_percent = tax_rate

        line_total = quantity * unit_price
        line.settlement.monetary_summation.total_amount = line_total

        total_net += line_total

        # Accumulate tax by rate
        rate_key = str(tax_rate)
        tax_amount = line_total * tax_rate / Decimal("100")
        if rate_key in tax_amounts:
            basis, tax = tax_amounts[rate_key]
            tax_amounts[rate_key] = (basis + line_total, tax + tax_amount)
        else:
            tax_amounts[rate_key] = (line_total, tax_amount)

        doc.trade.items.add(line)

    # Settlement
    doc.trade.settlement.currency_code = "EUR"

    # Payment means - bank transfer
    if vendor.iban:
        pm = PaymentMeans()
        pm.type_code = "58"  # SEPA credit transfer
        pm.payee_account.iban = vendor.iban
        if vendor.bic:
            pm.payee_institution.bic = vendor.bic
        doc.trade.settlement.payment_means.add(pm)

    # Payment terms
    if payment_terms_text or due_date:
        terms = PaymentTerms()
        if payment_terms_text:
            terms.description = payment_terms_text
        if due_date:
            terms.due = due_date
        doc.trade.settlement.terms.add(terms)

    # Tax breakdown
    total_tax = Decimal("0.00")
    for rate_str, (basis, tax) in tax_amounts.items():
        trade_tax = ApplicableTradeTax()
        trade_tax.calculated_amount = tax
        trade_tax.basis_amount = basis
        trade_tax.type_code = "VAT"
        trade_tax.category_code = "S"
        trade_tax.rate_applicable_percent = Decimal(rate_str)
        doc.trade.settlement.trade_tax.add(trade_tax)
        total_tax += tax

    # Monetary summation
    doc.trade.settlement.monetary_summation.line_total = total_net
    doc.trade.settlement.monetary_summation.charge_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.allowance_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.tax_basis_total = total_net
    doc.trade.settlement.monetary_summation.tax_total = (total_tax, "EUR")
    doc.trade.settlement.monetary_summation.grand_total = total_net + total_tax
    doc.trade.settlement.monetary_summation.prepaid_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.due_amount = total_net + total_tax

    # Generate XML
    return doc.serialize(schema="FACTUR-X_EN16931")


def save_zugferd_xml(xml_content: bytes, output_path: Path | str) -> None:
    """Save ZUGFeRD XML to a file.

    Args:
        xml_content: The XML bytes
        output_path: Path to save the file
    """
    path = Path(output_path)
    path.write_bytes(xml_content)
