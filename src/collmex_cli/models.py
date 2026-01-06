"""Pydantic models for Collmex record types.

Focused on Buchhaltung Pro use cases:
- Lieferanten (Vendors)
- Lieferantenrechnungen (Vendor Invoices)
- Offene Posten (Open Items)
- Buchungen (Accounting Documents)
"""

from datetime import date
from decimal import Decimal
from enum import IntEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator


def parse_collmex_date(value: str) -> date | None:
    """Parse Collmex date format (YYYYMMDD) to date object."""
    if not value:
        return None
    # Collmex uses YYYYMMDD format
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def format_collmex_date(value: date | None) -> str:
    """Format date to Collmex format (YYYYMMDD)."""
    if value is None:
        return ""
    return value.strftime("%Y%m%d")


def parse_collmex_decimal(value: str) -> Decimal | None:
    """Parse Collmex decimal format (German: comma as decimal separator)."""
    if not value:
        return None
    return Decimal(value.replace(",", "."))


def format_collmex_decimal(value: Decimal | None) -> str:
    """Format Decimal to Collmex format (German: comma as decimal separator)."""
    if value is None:
        return ""
    return str(value).replace(".", ",")


class OutputMedium(IntEnum):
    """Output medium for documents."""

    PRINT = 0
    EMAIL = 1
    FAX = 2
    LETTER = 3
    NONE = 100


class CollmexRecord(BaseModel):
    """Base class for Collmex records."""

    model_config = {"extra": "ignore"}

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        """Create a record from a CSV row."""
        raise NotImplementedError

    def to_csv_row(self) -> list[str]:
        """Convert record to CSV row for API submission."""
        raise NotImplementedError


# =============================================================================
# Vendor (Lieferant) - CMXLIF
# =============================================================================


class Vendor(CollmexRecord):
    """Collmex vendor/supplier record (CMXLIF).

    Used to create or update vendors in Collmex.
    """

    record_type: str = Field(default="CMXLIF", description="Record type identifier")
    vendor_id: int | None = Field(default=None, description="Vendor number (auto-assigned if empty)")
    company_id: int = Field(default=1, description="Company ID")
    salutation: str = Field(default="", description="Salutation")
    title: str = Field(default="", description="Title")
    first_name: str = Field(default="", description="First name")
    last_name: str = Field(default="", description="Last name")
    company_name: str = Field(default="", description="Company/firm name")
    department: str = Field(default="", description="Department")
    street: str = Field(default="", description="Street address")
    postal_code: str = Field(default="", description="Postal code")
    city: str = Field(default="", description="City")
    notes: str = Field(default="", description="Notes/remarks")
    inactive: int = Field(default=0, description="0=active, 1=inactive, 2/3=delete")
    country: str = Field(default="DE", description="Country code (ISO)")
    phone: str = Field(default="", description="Phone number")
    fax: str = Field(default="", description="Fax number")
    email: str = Field(default="", description="Email address")
    bank_account: str = Field(default="", description="Bank account number")
    bank_code: str = Field(default="", description="Bank code (BLZ)")
    iban: str = Field(default="", description="IBAN")
    bic: str = Field(default="", description="BIC/SWIFT code")
    bank_name: str = Field(default="", description="Bank name")
    tax_id: str = Field(default="", description="Tax ID (Steuernummer)")
    vat_id: str = Field(default="", description="VAT ID (USt-IdNr)")
    payment_terms: int = Field(default=0, description="Payment terms code")
    delivery_terms: str = Field(default="", description="Delivery terms (ISO)")
    delivery_terms_extra: str = Field(default="", description="Delivery terms additional")
    output_medium: int = Field(default=0, description="Output medium (0=print, 1=email, etc.)")
    account_holder: str = Field(default="", description="Bank account holder name")
    address_group: int | None = Field(default=None, description="Address group")
    customer_id: str | None = Field(default=None, description="Associated customer number")
    currency: str = Field(default="EUR", description="Currency (ISO)")
    private_person: int = Field(default=0, description="1 if private person")
    url: str = Field(default="", description="Website URL")

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        """Create Vendor from CSV row."""

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            val = get(idx)
            return int(val) if val else default

        return cls(
            record_type=get(0),
            vendor_id=get_int(1) or None,
            company_id=get_int(2, 1),
            salutation=get(3),
            title=get(4),
            first_name=get(5),
            last_name=get(6),
            company_name=get(7),
            department=get(8),
            street=get(9),
            postal_code=get(10),
            city=get(11),
            notes=get(12),
            inactive=get_int(13),
            country=get(14) or "DE",
            phone=get(15),
            fax=get(16),
            email=get(17),
            bank_account=get(18),
            bank_code=get(19),
            iban=get(20),
            bic=get(21),
            bank_name=get(22),
            tax_id=get(23),
            vat_id=get(24),
            payment_terms=get_int(25),
            delivery_terms=get(26),
            delivery_terms_extra=get(27),
            output_medium=get_int(28),
        )

    def to_csv_row(self) -> list[str]:
        """Convert to CSV row for creating/updating vendor."""
        return [
            self.record_type,
            str(self.vendor_id) if self.vendor_id else "",
            str(self.company_id),
            self.salutation,
            self.title,
            self.first_name,
            self.last_name,
            self.company_name,
            self.department,
            self.street,
            self.postal_code,
            self.city,
            self.notes,
            str(self.inactive),
            self.country,
            self.phone,
            self.fax,
            self.email,
            self.bank_account,
            self.bank_code,
            self.iban,
            self.bic,
            self.bank_name,
            self.tax_id,
            self.vat_id,
            str(self.payment_terms),
            self.delivery_terms,
            self.delivery_terms_extra,
            str(self.output_medium),
        ]


# =============================================================================
# Vendor Invoice (Lieferantenrechnung) - CMXLRN
# =============================================================================


class VendorInvoice(CollmexRecord):
    """Collmex vendor invoice record (CMXLRN).

    Used to book external vendor invoices or cash expenses in accounting.
    """

    record_type: str = Field(default="CMXLRN", description="Record type identifier")
    vendor_id: int | None = Field(default=None, description="Vendor number")
    company_id: int = Field(default=1, description="Company ID")
    invoice_date: date | None = Field(default=None, description="Invoice date")
    invoice_number: str = Field(default="", description="Invoice number (unique)")
    net_amount_full_tax: Decimal | None = Field(default=None, description="Net amount full VAT rate")
    tax_full: Decimal | None = Field(default=None, description="Tax amount full VAT (auto-calculated if empty)")
    net_amount_reduced_tax: Decimal | None = Field(default=None, description="Net amount reduced VAT rate")
    tax_reduced: Decimal | None = Field(default=None, description="Tax amount reduced VAT (auto-calculated)")
    other_account: int | None = Field(default=None, description="Account for other revenues (no tax)")
    other_amount: Decimal | None = Field(default=None, description="Amount for other account")
    currency: str = Field(default="EUR", description="Currency (ISO)")
    contra_account: int | None = Field(default=None, description="Contra account (default: 1600)")
    is_credit: bool = Field(default=False, description="True if credit note (reverses debit/credit)")
    booking_text: str = Field(default="", description="Booking text")
    payment_terms: int | None = Field(default=None, description="Payment terms code")
    account_full_tax: int | None = Field(default=None, description="Account for full tax (default: 3200)")
    account_reduced_tax: int | None = Field(default=None, description="Account for reduced tax (default: 3200)")
    is_cancelled: bool = Field(default=False, description="Is this a cancellation")
    cost_center: str = Field(default="", description="Cost center")
    memo: str = Field(default="", description="Internal memo")

    @field_validator("invoice_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date | None:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return parse_collmex_date(v)
        return None

    def to_csv_row(self) -> list[str]:
        """Convert to CSV row for creating vendor invoice."""
        return [
            self.record_type,
            str(self.vendor_id) if self.vendor_id else "",
            str(self.company_id),
            format_collmex_date(self.invoice_date),
            self.invoice_number,
            format_collmex_decimal(self.net_amount_full_tax),
            format_collmex_decimal(self.tax_full),
            format_collmex_decimal(self.net_amount_reduced_tax),
            format_collmex_decimal(self.tax_reduced),
            str(self.other_account) if self.other_account else "",
            format_collmex_decimal(self.other_amount),
            self.currency,
            str(self.contra_account) if self.contra_account else "",
            "1" if self.is_credit else "",
            self.booking_text,
            str(self.payment_terms) if self.payment_terms is not None else "",
            str(self.account_full_tax) if self.account_full_tax else "",
            str(self.account_reduced_tax) if self.account_reduced_tax else "",
            "1" if self.is_cancelled else "",
            self.cost_center,
            self.memo,
        ]


# =============================================================================
# Open Item (Offener Posten) - OPEN_ITEM
# =============================================================================


class OpenItem(CollmexRecord):
    """Collmex open item record (OPEN_ITEM).

    Represents unpaid invoices (receivables or payables).
    """

    record_type: str = Field(default="OPEN_ITEM", description="Record type identifier")
    company_id: int = Field(default=1, description="Company ID")
    fiscal_year: int = Field(default=0, description="Fiscal year")
    booking_id: int = Field(default=0, description="Booking number")
    position: int = Field(default=0, description="Position number")
    customer_id: int | None = Field(default=None, description="Customer number")
    customer_name: str = Field(default="", description="Customer name")
    vendor_id: int | None = Field(default=None, description="Vendor number")
    vendor_name: str = Field(default="", description="Vendor name")
    invoice_number: str = Field(default="", description="Invoice number")
    document_date: date | None = Field(default=None, description="Document date")
    payment_terms: int = Field(default=0, description="Payment terms code")
    due_date: date | None = Field(default=None, description="Due date")
    days_overdue: int = Field(default=0, description="Days overdue")
    dunning_level: int = Field(default=0, description="Dunning level")
    dunning_date: date | None = Field(default=None, description="Last dunning date")
    dunning_fees: Decimal | None = Field(default=None, description="Total dunning fees")
    amount: Decimal | None = Field(default=None, description="Total amount")
    paid: Decimal | None = Field(default=None, description="Amount paid")
    open_amount: Decimal | None = Field(default=None, description="Open amount")

    @field_validator("document_date", "due_date", "dunning_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date | None:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return parse_collmex_date(v)
        return None

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        """Create OpenItem from CSV row."""

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            val = get(idx)
            return int(val) if val else default

        return cls(
            record_type=get(0),
            company_id=get_int(1, 1),
            fiscal_year=get_int(2),
            booking_id=get_int(3),
            position=get_int(4),
            customer_id=get_int(5) or None,
            customer_name=get(6),
            vendor_id=get_int(7) or None,
            vendor_name=get(8),
            invoice_number=get(9),
            document_date=get(10),
            payment_terms=get_int(11),
            due_date=get(12),
            days_overdue=get_int(13),
            dunning_level=get_int(14),
            dunning_date=get(15),
            dunning_fees=parse_collmex_decimal(get(16)),
            amount=parse_collmex_decimal(get(17)),
            paid=parse_collmex_decimal(get(18)),
            open_amount=parse_collmex_decimal(get(19)),
        )


# =============================================================================
# Accounting Document (Buchung) - ACCDOC
# =============================================================================


class AccountingDocument(CollmexRecord):
    """Collmex accounting document record (ACCDOC).

    Represents a single booking/journal entry line.
    """

    record_type: str = Field(default="ACCDOC", description="Record type identifier")
    company_id: int = Field(default=1, description="Company ID")
    fiscal_year: int = Field(default=0, description="Fiscal year")
    booking_id: int = Field(default=0, description="Booking number")
    document_date: date | None = Field(default=None, description="Document date")
    booked_date: date | None = Field(default=None, description="Date when booked")
    booking_text: str = Field(default="", description="Booking text")
    position: int = Field(default=0, description="Position number")
    account_number: int = Field(default=0, description="Account number")
    account_name: str = Field(default="", description="Account name")
    debit_credit: str = Field(default="", description="S=Debit, H=Credit")
    amount: Decimal | None = Field(default=None, description="Amount")
    customer_id: int | None = Field(default=None, description="Customer number")
    customer_name: str = Field(default="", description="Customer name")
    vendor_id: int | None = Field(default=None, description="Vendor number")
    vendor_name: str = Field(default="", description="Vendor name")
    asset_id: int | None = Field(default=None, description="Asset number")
    asset_name: str = Field(default="", description="Asset name")
    cancelled_booking: int | None = Field(default=None, description="Original booking if cancelled")
    cost_center: str = Field(default="", description="Cost center")
    invoice_number: str = Field(default="", description="Invoice number")
    customer_order_id: int | None = Field(default=None, description="Customer order ID")
    travel_id: int | None = Field(default=None, description="Travel ID")
    supplier_order_id: int | None = Field(default=None, description="Supplier order ID")
    payment_id: int | None = Field(default=None, description="Payment ID")
    document_number: str = Field(default="", description="Document/receipt number")
    memo: str = Field(default="", description="Internal memo")
    user: str = Field(default="", description="User who created the entry")

    @field_validator("document_date", "booked_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date | None:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            return parse_collmex_date(v)
        return None

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        """Create AccountingDocument from CSV row."""

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            val = get(idx)
            return int(val) if val else default

        return cls(
            record_type=get(0),
            company_id=get_int(1, 1),
            fiscal_year=get_int(2),
            booking_id=get_int(3),
            document_date=get(4),
            booked_date=get(5),
            booking_text=get(6),
            position=get_int(7),
            account_number=get_int(8),
            account_name=get(9),
            debit_credit=get(10),
            amount=parse_collmex_decimal(get(11)),
            customer_id=get_int(12) or None,
            customer_name=get(13),
            vendor_id=get_int(14) or None,
            vendor_name=get(15),
            asset_id=get_int(16) or None,
            asset_name=get(17),
            cancelled_booking=get_int(18) or None,
            cost_center=get(19),
            invoice_number=get(20),
            customer_order_id=get_int(21) or None,
            travel_id=get_int(22) or None,
            supplier_order_id=get_int(23) or None,
            payment_id=get_int(24) or None,
            document_number=get(25),
            memo=get(26),
            user=get(27),
        )


# =============================================================================
# Record type mapping
# =============================================================================

RECORD_TYPES: dict[str, type[CollmexRecord]] = {
    "CMXLIF": Vendor,
    "OPEN_ITEM": OpenItem,
    "ACCDOC": AccountingDocument,
}


def parse_record(row: list[str]) -> CollmexRecord | None:
    """Parse a CSV row into the appropriate record type.

    Args:
        row: CSV row data

    Returns:
        Parsed record or None if record type is unknown
    """
    if not row:
        return None

    record_type = row[0]
    model_class = RECORD_TYPES.get(record_type)

    if model_class is None:
        return None

    return model_class.from_csv_row(row)
