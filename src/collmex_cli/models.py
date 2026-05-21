"""Pydantic models for Collmex record types.

Focused on Buchhaltung Pro use cases:
- Lieferanten (Vendors)
- Lieferantenrechnungen (Vendor Invoices)
- Offene Posten (Open Items)
- Buchungen (Accounting Documents)
"""

import re
from datetime import date
from decimal import Decimal
from enum import IntEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator


def _parse_int(value: str, default: int = 0) -> int:
    """Parse an int from a Collmex field that may contain trailing text.

    The Collmex API sometimes returns compound values like "1 cognovís GmbH"
    for integer fields. This extracts just the leading number.
    """
    if not value:
        return default
    m = re.match(r"^\s*(-?\d+)", value)
    return int(m.group(1)) if m else default


def parse_collmex_date(value: str) -> date | None:
    """Parse Collmex date format (YYYYMMDD) to date object.

    Handles float-formatted strings (e.g. "20260201.0") that occur when
    Collmex returns numeric date values that get parsed as floats.
    """
    if not value:
        return None
    # Handle float-formatted strings like "20260201.0"
    if "." in value:
        try:
            value = str(int(float(value)))
        except (ValueError, OverflowError):
            return None
    # Need exactly 8 digits for YYYYMMDD; short/zero values mean "no date"
    if len(value) < 8:
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
            return _parse_int(get(idx), default)

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
# Customer (Kunde) - CMXKND
# =============================================================================


class Customer(CollmexRecord):
    """Collmex customer record (CMXKND).

    Field order matches official Collmex API spec (Satzbeschreibung Kunde).
    Used to create or update customers in Collmex.
    """

    # Fields 1-12: Identity & address
    record_type: str = Field(default="CMXKND", description="Record type identifier")
    customer_id: int | None = Field(default=None, description="Customer number (auto-assigned if empty)")
    company_id: int = Field(default=1, description="Company ID (Firma Nr)")
    salutation: str = Field(default="", description="Salutation (Anrede)")
    title: str = Field(default="", description="Title (Titel)")
    first_name: str = Field(default="", description="First name (Vorname)")
    last_name: str = Field(default="", description="Last name (Name)")
    company_name: str = Field(default="", description="Company/firm name (Firma)")
    department: str = Field(default="", description="Department (Abteilung)")
    street: str = Field(default="", description="Street address (Straße)")
    zip_code: str = Field(default="", description="Postal code (PLZ)")
    city: str = Field(default="", description="City (Ort)")
    # Fields 13-15: Notes, status, country
    notes: str = Field(default="", description="Notes/remarks (Bemerkung)")
    inactive: int = Field(default=0, description="0=active, 1=inactive, 2/3=delete (Inaktiv)")
    country: str = Field(default="DE", description="Country code ISO 2-letter (Land)")
    # Fields 16-18: Contact
    phone: str = Field(default="", description="Phone number (Telefon)")
    fax: str = Field(default="", description="Fax number (Telefax)")
    email: str = Field(default="", description="Email address (E-Mail)")
    # Fields 19-23: Banking
    bank_account: str = Field(default="", description="Bank account number (Kontonummer)")
    bank_code: str = Field(default="", description="Bank code BLZ (Blz)")
    iban: str = Field(default="", description="IBAN")
    bic: str = Field(default="", description="BIC/SWIFT code")
    bank_name: str = Field(default="", description="Bank name (Bankname)")
    # Field 24: Reserved (Reserviert) — not stored
    # Field 25: VAT ID
    vat_id: str = Field(default="", description="VAT ID (USt.IdNr)")
    # Fields 26-30: Conditions & output
    payment_condition: int = Field(default=0, description="Payment condition code (Zahlungsbedingung)")
    discount_group: int = Field(default=0, description="Discount group (Rabattgruppe)")
    delivery_condition: str = Field(default="", description="Delivery condition INCOTERMS (Lieferbedingung)")
    delivery_condition_extra: str = Field(default="", description="Delivery condition addendum (Lieferbedingung Zusatz)")
    output_medium: int = Field(default=0, description="Output medium: 0=Druck, 1=E-Mail, 2=Fax, 3=Brief, 100=keine (Ausgabemedium)")
    # Fields 31-36: Account & grouping
    bank_owner: str = Field(default="", description="Bank account holder if different (Kontoinhaber)")
    address_group: str = Field(default="", description="Address group with optional note (Adressgruppe)")
    ebay_name: str = Field(default="", description="eBay member name (eBay-Mitgliedsname)")
    price_group: int = Field(default=0, description="Price group (Preisgruppe)")
    currency: str = Field(default="EUR", description="Currency ISO code (Währung)")
    agent: int = Field(default=0, description="Agent/broker employee number (Vermittler)")
    # Fields 37-41: Misc
    cost_center: str = Field(default="", description="Cost center (Kostenstelle)")
    followup_date: str = Field(default="", description="Follow-up date YYYYMMDD (Wiedervorlage am)")
    delivery_block: int = Field(default=0, description="1=delivery blocked (Liefersperre)")
    construction_service: int = Field(default=0, description="1=Bau/Reinigungs-Dienstleister")
    supplier_number_at_customer: str = Field(default="", description="Own supplier number at customer (Lief-Nr. bei Kunde)")
    # Fields 42-50: More contact & options
    output_language: int = Field(default=0, description="Output language: 0=Deutsch, 1=Englisch (Ausgabesprache)")
    cc_email: str = Field(default="", description="CC email address (CC)")
    phone2: str = Field(default="", description="Second phone number (Telefon2)")
    direct_debit_mandate_ref: str = Field(default="", description="Direct debit mandate reference (Lastschrift-Mandatsreferenz)")
    direct_debit_signature_date: str = Field(default="", description="Direct debit signature date YYYYMMDD (Datum Unterschrift)")
    dunning_block: int = Field(default=0, description="1=dunning blocked (Mahnsperre)")
    no_mailings: int = Field(default=0, description="1=no mailings (Keine Mailings)")
    private_person: int = Field(default=0, description="1=private person (Privatperson)")
    url: str = Field(default="", description="Website URL")
    # Fields 51-54: Delivery/invoice options & meta
    partial_deliveries: int = Field(default=0, description="1=partial deliveries allowed (Teil-Lieferungen erlaubt)")
    partial_invoices: int = Field(default=0, description="1=partial invoices allowed (Teil-Rechnungen erlaubt)")
    created_at: str = Field(default="", description="Creation date export-only (Angelegt am)")
    invoice_format: int = Field(default=0, description="0=PDF+XML, 1=only XML, 2=only PDF (Rechnungsformat)")

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "Customer":
        """Create Customer from CSV row (official CMXKND field order)."""

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            return _parse_int(get(idx), default)

        return cls(
            record_type=get(0),
            customer_id=get_int(1) or None,
            company_id=get_int(2, 1),
            salutation=get(3),
            title=get(4),
            first_name=get(5),
            last_name=get(6),
            company_name=get(7),
            department=get(8),
            street=get(9),
            zip_code=get(10),
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
            # field 23 = Reserviert (skip)
            vat_id=get(24),
            payment_condition=get_int(25),
            discount_group=get_int(26),
            delivery_condition=get(27),
            delivery_condition_extra=get(28),
            output_medium=get_int(29),
            bank_owner=get(30),
            address_group=get(31),
            ebay_name=get(32),
            price_group=get_int(33),
            currency=get(34) or "EUR",
            agent=get_int(35),
            cost_center=get(36),
            followup_date=get(37),
            delivery_block=get_int(38),
            construction_service=get_int(39),
            supplier_number_at_customer=get(40),
            output_language=get_int(41),
            cc_email=get(42),
            phone2=get(43),
            direct_debit_mandate_ref=get(44),
            direct_debit_signature_date=get(45),
            dunning_block=get_int(46),
            no_mailings=get_int(47),
            private_person=get_int(48),
            url=get(49),
            partial_deliveries=get_int(50),
            partial_invoices=get_int(51),
            created_at=get(52),
            invoice_format=get_int(53),
        )

    def to_csv_row(self) -> list[str]:
        """Convert to CSV row for creating/updating customer (official CMXKND field order)."""
        return [
            self.record_type,                                              # 1
            str(self.customer_id) if self.customer_id else "",            # 2
            str(self.company_id),                                          # 3
            self.salutation,                                               # 4
            self.title,                                                    # 5
            self.first_name,                                               # 6
            self.last_name,                                                # 7
            self.company_name,                                             # 8
            self.department,                                               # 9
            self.street,                                                   # 10
            self.zip_code,                                                 # 11
            self.city,                                                     # 12
            self.notes,                                                    # 13
            str(self.inactive),                                            # 14
            self.country,                                                  # 15
            self.phone,                                                    # 16
            self.fax,                                                      # 17
            self.email,                                                    # 18
            self.bank_account,                                             # 19
            self.bank_code,                                                # 20
            self.iban,                                                     # 21
            self.bic,                                                      # 22
            self.bank_name,                                                # 23
            "",                                                            # 24 Reserviert
            self.vat_id,                                                   # 25
            str(self.payment_condition),                                   # 26
            str(self.discount_group),                                      # 27
            self.delivery_condition,                                       # 28
            self.delivery_condition_extra,                                 # 29
            str(self.output_medium),                                       # 30
            self.bank_owner,                                               # 31
            self.address_group,                                            # 32
            self.ebay_name,                                                # 33
            str(self.price_group),                                         # 34
            self.currency,                                                 # 35
            str(self.agent),                                               # 36
            self.cost_center,                                              # 37
            self.followup_date,                                            # 38
            str(self.delivery_block),                                      # 39
            str(self.construction_service),                                # 40
            self.supplier_number_at_customer,                              # 41
            str(self.output_language),                                     # 42
            self.cc_email,                                                 # 43
            self.phone2,                                                   # 44
            self.direct_debit_mandate_ref,                                 # 45
            self.direct_debit_signature_date,                              # 46
            str(self.dunning_block),                                       # 47
            str(self.no_mailings),                                         # 48
            str(self.private_person),                                      # 49
            self.url,                                                      # 50
            str(self.partial_deliveries),                                  # 51
            str(self.partial_invoices),                                    # 52
            # 53 (created_at) is export-only, omit on write
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
        if isinstance(v, (int, float)):
            v = str(int(v))
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
# Customer Invoice - CMXUMS
# =============================================================================


class CustomerInvoice(CollmexRecord):
    """Collmex customer invoice record (CMXUMS).

    Used to book external customer invoices in accounting without the invoicing
    module. Field 15 stays empty so Collmex books the receivable account and
    creates an open item for the customer.
    """

    record_type: str = Field(default="CMXUMS", description="Record type identifier")
    customer_id: int | None = Field(default=None, description="Customer number")
    company_id: int = Field(default=1, description="Company ID")
    invoice_date: date | None = Field(default=None, description="Invoice date")
    invoice_number: str = Field(default="", description="Invoice number (unique)")
    net_amount_full_tax: Decimal | None = Field(default=None, description="Net amount full VAT rate")
    tax_full: Decimal | None = Field(default=None, description="Tax amount full VAT")
    net_amount_reduced_tax: Decimal | None = Field(default=None, description="Net amount reduced VAT rate")
    tax_reduced: Decimal | None = Field(default=None, description="Tax amount reduced VAT")
    is_credit: bool = Field(default=False, description="True if credit note")
    booking_text: str = Field(default="", description="Booking text")
    payment_terms: str = Field(default="", description="Payment terms or due date")
    account_full_tax: int | None = Field(default=None, description="Revenue account for full tax")

    @field_validator("invoice_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date | None:
        if isinstance(v, date):
            return v
        if isinstance(v, (int, float)):
            v = str(int(v))
        if isinstance(v, str):
            if "-" in v:
                return date.fromisoformat(v)
            return parse_collmex_date(v)
        return None

    def to_csv_row(self) -> list[str]:
        """Convert to CSV row for creating a customer invoice."""
        return [
            self.record_type,
            str(self.customer_id) if self.customer_id else "",
            str(self.company_id),
            format_collmex_date(self.invoice_date),
            self.invoice_number,
            format_collmex_decimal(self.net_amount_full_tax),
            format_collmex_decimal(self.tax_full),
            format_collmex_decimal(self.net_amount_reduced_tax),
            format_collmex_decimal(self.tax_reduced),
            "",
            "",
            "",
            "",
            "",
            "",
            "1" if self.is_credit else "0",
            self.booking_text,
            self.payment_terms,
            str(self.account_full_tax) if self.account_full_tax else "",
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
        if isinstance(v, (int, float)):
            v = str(int(v))
        if isinstance(v, str):
            return parse_collmex_date(v)
        return None

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        """Create OpenItem from CSV row."""

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            return _parse_int(get(idx), default)

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
        if isinstance(v, (int, float)):
            v = str(int(v))
        if isinstance(v, str):
            return parse_collmex_date(v)
        return None

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Self:
        """Create AccountingDocument from CSV row."""

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            return _parse_int(get(idx), default)

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
# Account Balance (Kontosaldo) - ACC_BAL
# =============================================================================


class AccountBalance(CollmexRecord):
    """Collmex account balance record (ACC_BAL).

    Returned by ACCBAL_GET queries. Real API response format:
    ACC_BAL;<account_number>;<account_name>;<balance>

    Four fields only — no company_id, fiscal_year, opening_balance, or turnover
    in the actual response.
    """

    record_type: str = Field(default="ACC_BAL", description="Record type identifier")
    account_number: int = Field(default=0, description="Account number (Kontonummer)")
    account_name: str = Field(default="", description="Account name (Kontobezeichnung)")
    balance: Decimal | None = Field(default=None, description="Current balance (Saldo)")

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "AccountBalance":
        """Create AccountBalance from CSV row.

        Real format: ['ACC_BAL', account_number, account_name, balance]
        """

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        return cls(
            record_type=get(0),
            account_number=_parse_int(get(1)),
            account_name=get(2),
            balance=parse_collmex_decimal(get(3)),
        )

    def to_csv_row(self) -> list[str]:
        """Convert to CSV row (ACC_BAL is a read response type)."""
        return [
            self.record_type,
            str(self.account_number),
            self.account_name,
            format_collmex_decimal(self.balance),
        ]


# =============================================================================
# Invoice Payment (Rechnungszahlung) - INVOICE_PAYMENT
# =============================================================================


class InvoicePayment(CollmexRecord):
    """Collmex invoice payment record (INVOICE_PAYMENT).

    Represents a payment received for a customer invoice.
    Returned by INVOICE_PAYMENT_GET queries.

    Official API field layout (source: https://www.collmex.de/handbuch_buchhaltung_pro.html#api):
      1: Satzart          — INVOICE_PAYMENT
      2: Rechnungsnummer  — Invoice number
      3: Datum            — Payment date (YYYYMMDD)
      4: Gezahlter Betrag — Actually paid via bank/cash
      5: Reduzierender Betrag — Open item reduced by this amount (may differ due to Skonto)
      6: Geschäftsjahr    — Fiscal year of the booking
      7: BuchungNr        — Booking number
      8: BuchungPos       — Booking position
      9: Systemname       — External system name

    Note: Geschäftsjahr + BuchungNr + BuchungPos uniquely identify a payment.
    When a payment is reversed, Datum and Betrag are empty.
    """

    record_type: str = Field(default="INVOICE_PAYMENT", description="Record type identifier")
    invoice_number: str = Field(default="", description="Invoice number (Rechnungsnummer)")
    payment_date: date | None = Field(default=None, description="Payment date (Datum)")
    payment_amount: Decimal | None = Field(default=None, description="Actually paid amount (Gezahlter Betrag)")
    reducing_amount: Decimal | None = Field(default=None, description="Open item reduction (Reduzierender Betrag) — may differ due to Skonto/discounts")
    fiscal_year: int = Field(default=0, description="Fiscal year of booking (Geschäftsjahr)")
    booking_id: int | None = Field(default=None, description="Booking number (BuchungNr)")
    booking_position: int | None = Field(default=None, description="Booking position (BuchungPos)")
    system_name: str = Field(default="", description="External system name (Systemname)")

    @field_validator("payment_date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date | None:
        if isinstance(v, date):
            return v
        if isinstance(v, (int, float)):
            v = str(int(v))
        if isinstance(v, str):
            return parse_collmex_date(v)
        return None

    @classmethod
    def from_csv_row(cls, row: list[str]) -> "InvoicePayment":
        """Create InvoicePayment from CSV row.

        Field indices are 0-based (CSV row[0] = Satzart = field 1 in docs).
        """

        def get(idx: int, default: str = "") -> str:
            return row[idx] if idx < len(row) else default

        def get_int(idx: int, default: int = 0) -> int:
            return _parse_int(get(idx), default)

        return cls(
            record_type=get(0),
            invoice_number=get(1).strip(),
            payment_date=get(2),
            payment_amount=parse_collmex_decimal(get(3)),
            reducing_amount=parse_collmex_decimal(get(4)),
            fiscal_year=get_int(5),
            booking_id=get_int(6) or None,
            booking_position=get_int(7) or None,
            system_name=get(8),
        )

# =============================================================================
# Record type mapping
# =============================================================================

RECORD_TYPES: dict[str, type[CollmexRecord]] = {
    "CMXLIF": Vendor,
    "CMXKND": Customer,
    "OPEN_ITEM": OpenItem,
    "ACCDOC": AccountingDocument,
    "ACC_BAL": AccountBalance,
    "INVOICE_PAYMENT": InvoicePayment,
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


# =============================================================================
# Invoice (Kundenrechnung) - CMXINV
# =============================================================================


class InvoiceLine(BaseModel):
    """A single line item of a Collmex invoice (CMXINV, position > 0)."""

    model_config = {"extra": "ignore"}

    position: int = Field(default=0, description="Position number")
    text: str = Field(default="", description="Position text/description")
    quantity: Decimal | None = Field(default=None, description="Quantity")
    unit: str = Field(default="", description="Unit of measure")
    price: Decimal | None = Field(default=None, description="Unit price")
    price_type: int = Field(default=0, description="0=gross, 1=net")
    vat_rate: Decimal | None = Field(default=None, description="VAT rate (%)")
    product_id: str = Field(default="", description="Product/article ID")
    product_type: int = Field(default=0, description="Product type")
    revenue_account: int | None = Field(default=None, description="Revenue account")
    cost_center: int | None = Field(default=None, description="Cost center")
    total_net: Decimal | None = Field(default=None, description="Line net total")
    total_vat: Decimal | None = Field(default=None, description="Line VAT total")
    total_gross: Decimal | None = Field(default=None, description="Line gross total")


class Invoice(BaseModel):
    """A Collmex customer invoice (CMXINV), assembled from header + line rows."""

    model_config = {"extra": "ignore"}

    invoice_id: int = Field(default=0, description="Invoice number")
    invoice_type: int = Field(default=0, description="0=Rechnung, 1=Gutschrift, 2=Lieferschein")
    customer_id: int | None = Field(default=None, description="Customer number")
    customer_salutation: str = Field(default="", description="Customer salutation")
    customer_title: str = Field(default="", description="Customer title")
    customer_company: str = Field(default="", description="Customer company name")
    customer_first_name: str = Field(default="", description="Customer first name")
    customer_last_name: str = Field(default="", description="Customer last name")
    customer_street: str = Field(default="", description="Customer street")
    customer_zip: str = Field(default="", description="Customer postal code")
    customer_city: str = Field(default="", description="Customer city")
    customer_country: str = Field(default="", description="Customer country")
    customer_phone: str = Field(default="", description="Customer phone")
    customer_fax: str = Field(default="", description="Customer fax")
    customer_email: str = Field(default="", description="Customer email")
    invoice_date: date | None = Field(default=None, description="Invoice date")
    payment_term: int = Field(default=0, description="Payment term code")
    discount_days: int = Field(default=0, description="Discount days")
    discount_percent: Decimal | None = Field(default=None, description="Discount percentage")
    currency: str = Field(default="EUR", description="Currency (ISO)")
    price_group: int = Field(default=0, description="Price group")
    discount_total: Decimal | None = Field(default=None, description="Total discount")
    due_date: date | None = Field(default=None, description="Due date")
    total_net: Decimal | None = Field(default=None, description="Total net amount")
    total_vat: Decimal | None = Field(default=None, description="Total VAT amount")
    total_gross: Decimal | None = Field(default=None, description="Total gross amount")
    cancelled: int = Field(default=0, description="0=active, 1=cancelled")
    invoice_number_text: str = Field(default="", description="Human-readable invoice number")
    lines: list[InvoiceLine] = Field(default_factory=list, description="Invoice line items")

    @classmethod
    def from_cmxinv_rows(cls, rows: list[list[str]]) -> list["Invoice"]:
        """Parse a list of CMXINV rows into grouped Invoice objects.

        Rows with position=0 are header rows; rows with position>0 are line items.
        Invoices are grouped by invoice_id.
        """
        invoices_map: dict[int, "Invoice"] = {}

        for row in rows:
            if not row or row[0] != "CMXINV":
                continue

            def get(idx: int, default: str = "", _row: list[str] = row) -> str:
                return _row[idx] if idx < len(_row) else default

            def get_int(idx: int, default: int = 0, _row: list[str] = row) -> int:
                return _parse_int(get(idx, str(default), _row), default)

            invoice_id = get_int(1)
            position = get_int(2)

            if position == 0:
                inv = cls(
                    invoice_id=invoice_id,
                    invoice_type=get_int(3),
                    customer_id=get_int(4) or None,
                    customer_salutation=get(5),
                    customer_title=get(6),
                    customer_company=get(7),
                    customer_first_name=get(8),
                    customer_last_name=get(9),
                    customer_street=get(10),
                    customer_zip=get(11),
                    customer_city=get(12),
                    customer_country=get(13),
                    customer_phone=get(14),
                    customer_fax=get(15),
                    customer_email=get(16),
                    invoice_date=parse_collmex_date(get(18)),
                    payment_term=get_int(19),
                    discount_days=get_int(22),
                    discount_percent=parse_collmex_decimal(get(23)),
                    currency=get(26) or "EUR",
                    price_group=get_int(27),
                    discount_total=parse_collmex_decimal(get(28)),
                    due_date=parse_collmex_date(get(31)),
                    total_net=parse_collmex_decimal(get(50)),
                    total_vat=parse_collmex_decimal(get(51)),
                    total_gross=parse_collmex_decimal(get(52)),
                    cancelled=get_int(56),
                    invoice_number_text=get(57),
                )
                invoices_map[invoice_id] = inv
            else:
                if invoice_id not in invoices_map:
                    invoices_map[invoice_id] = cls(invoice_id=invoice_id)

                line = InvoiceLine(
                    position=position,
                    text=get(33),
                    quantity=parse_collmex_decimal(get(34)),
                    unit=get(35),
                    price=parse_collmex_decimal(get(36)),
                    price_type=get_int(37),
                    vat_rate=parse_collmex_decimal(get(38)),
                    product_id=get(39),
                    product_type=get_int(40),
                    revenue_account=get_int(42) or None,
                    cost_center=get_int(44) or None,
                    total_net=parse_collmex_decimal(get(50)),
                    total_vat=parse_collmex_decimal(get(51)),
                    total_gross=parse_collmex_decimal(get(52)),
                )
                invoices_map[invoice_id].lines.append(line)

        return list(invoices_map.values())
