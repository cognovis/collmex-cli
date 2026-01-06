"""ZUGFeRD XML generation for vendor invoices.

Uses python-drafthorse to generate EN 16931 compliant XML.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentTerms
from drafthorse.models.tradelines import LineItem

from .config import CollmexConfig, get_config
from .models import Vendor


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
) -> str:
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
        XML string in UN/CEFACT CII format (EN 16931)
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
        note.content.add(notes)
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
        doc.trade.agreement.seller.electronic_address.add(
            (vendor.email, "EM")
        )

    if vendor.vat_id:
        tax_reg = TaxRegistration()
        tax_reg.id = (vendor.vat_id, "VA")
        doc.trade.agreement.seller.tax_registrations.add(tax_reg)

    # Buyer (your company) party
    doc.trade.agreement.buyer.name = config.buyer_name

    if buyer_customer_id:
        doc.trade.agreement.buyer.id.add(buyer_customer_id)

    if config.buyer_street:
        doc.trade.agreement.buyer.address.line_one = config.buyer_street
    if config.buyer_zip:
        doc.trade.agreement.buyer.address.postcode = config.buyer_zip
    if config.buyer_city:
        doc.trade.agreement.buyer.address.city_name = config.buyer_city
    doc.trade.agreement.buyer.address.country_id = config.buyer_country

    if config.buyer_email:
        doc.trade.agreement.buyer.electronic_address.add(
            (config.buyer_email, "EM")
        )

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
        doc.trade.settlement.payment_means.type_code = "58"  # SEPA credit transfer
        doc.trade.settlement.payment_means.payee_account.iban = vendor.iban
        if vendor.bic:
            doc.trade.settlement.payment_means.payee_institution.bic = vendor.bic

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
    doc.trade.settlement.monetary_summation.due_payable = total_net + total_tax

    # Generate XML
    return doc.serialize(schema="FACTUR-X_EN16931")


def save_zugferd_xml(xml_content: str, output_path: Path | str) -> None:
    """Save ZUGFeRD XML to a file.

    Args:
        xml_content: The XML string
        output_path: Path to save the file
    """
    path = Path(output_path)
    path.write_text(xml_content, encoding="utf-8")
