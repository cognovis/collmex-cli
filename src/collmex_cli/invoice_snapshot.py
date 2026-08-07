"""Normalized, validated input for outgoing ZUGFeRD documents."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CountryCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{2}$")]
CurrencyCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$")]
Amount = Annotated[Decimal, Field(ge=Decimal("0.00"))]
PositiveAmount = Annotated[Decimal, Field(gt=Decimal("0.00"))]
TaxCategoryCode = Literal["S", "Z", "AE", "G"]


class InvoiceSnapshotError(ValueError):
    """A safe invoice validation error containing only object IDs and field names."""

    def __init__(self, object_id: int, fields: list[str]) -> None:
        self.object_id = object_id
        self.fields = sorted(set(fields))
        super().__init__(f"Invoice {object_id} has invalid fields: {', '.join(self.fields)}")


class PartySnapshot(BaseModel):
    """Seller or buyer master data needed by EN 16931."""

    model_config = ConfigDict(extra="forbid")

    object_id: int
    name: NonEmptyString
    street: NonEmptyString
    postal_code: NonEmptyString
    city: NonEmptyString
    country_code: CountryCode
    vat_id: NonEmptyString | None = None


class InvoiceLineSnapshot(BaseModel):
    """One normalized invoice or credit-note line."""

    model_config = ConfigDict(extra="forbid")

    object_id: int
    description: NonEmptyString
    quantity: PositiveAmount
    unit_code: NonEmptyString
    unit_price: Amount
    tax_rate: Amount
    line_total: Amount
    tax_category_code: TaxCategoryCode | None = None

    @property
    def effective_tax_category_code(self) -> TaxCategoryCode:
        """Return the supplied EN 16931 VAT category or a rate-based default."""
        if self.tax_category_code is not None:
            return self.tax_category_code
        return "Z" if _money(self.tax_rate) == Decimal("0.00") else "S"


class TaxSnapshot(BaseModel):
    """One VAT breakdown row from the source invoice."""

    model_config = ConfigDict(extra="forbid")

    rate: Amount
    basis_amount: Amount
    tax_amount: Amount
    category_code: TaxCategoryCode | None = None

    @property
    def effective_category_code(self) -> TaxCategoryCode:
        """Return the supplied EN 16931 VAT category or a rate-based default."""
        if self.category_code is not None:
            return self.category_code
        return "Z" if _money(self.rate) == Decimal("0.00") else "S"


class InvoiceTotalsSnapshot(BaseModel):
    """Source totals that must reconcile with lines and taxes."""

    model_config = ConfigDict(extra="forbid")

    line_total: Amount
    tax_basis_total: Amount
    tax_total: Amount
    grand_total: Amount
    due_amount: Amount


class InvoiceSnapshot(BaseModel):
    """The single source of truth for a generated outgoing document pair."""

    model_config = ConfigDict(extra="forbid")

    object_id: int
    document_kind: Literal["invoice", "credit_note"]
    document_number: NonEmptyString
    issue_date: date
    delivery_date: date
    currency: CurrencyCode
    seller: PartySnapshot
    buyer: PartySnapshot
    lines: Annotated[list[InvoiceLineSnapshot], Field(min_length=1)]
    taxes: Annotated[list[TaxSnapshot], Field(min_length=1)]
    totals: InvoiceTotalsSnapshot
    payment_terms: NonEmptyString
    due_date: date
    payment_means_type_code: Literal["10", "20", "58"]
    payee_iban: NonEmptyString | None = None
    payee_bic: NonEmptyString | None = None

    @model_validator(mode="after")
    def reconcile_amounts(self) -> Self:
        """Reject any disagreement between source lines, VAT breakdowns, and totals."""
        invalid_fields: list[str] = []
        basis_by_category: dict[tuple[Decimal, TaxCategoryCode], Decimal] = {}

        for index, line in enumerate(self.lines):
            expected_line_total = _money(line.quantity * line.unit_price)
            if _money(line.line_total) != expected_line_total:
                invalid_fields.append(f"lines.{index}.line_total")
            category_code = line.effective_tax_category_code
            if not _valid_tax_category(line.tax_rate, category_code):
                invalid_fields.append(f"lines.{index}.tax_category_code")
            rate = _money(line.tax_rate)
            tax_key = (rate, category_code)
            basis_by_category[tax_key] = _money(
                basis_by_category.get(tax_key, Decimal("0.00")) + line.line_total
            )

        declared_categories: set[tuple[Decimal, TaxCategoryCode]] = set()
        for index, tax in enumerate(self.taxes):
            rate = _money(tax.rate)
            category_code = tax.effective_category_code
            tax_key = (rate, category_code)
            declared_categories.add(tax_key)
            if _money(tax.basis_amount) != basis_by_category.get(tax_key):
                invalid_fields.append(f"taxes.{index}.basis_amount")
            expected_tax = _money(basis_by_category.get(tax_key, Decimal("0.00")) * rate / Decimal(100))
            if _money(tax.tax_amount) != expected_tax:
                invalid_fields.append(f"taxes.{index}.tax_amount")
            if not _valid_tax_category(tax.rate, category_code):
                invalid_fields.append(f"taxes.{index}.category_code")

        if declared_categories != set(basis_by_category):
            invalid_fields.append("taxes")
        if self.seller.vat_id is None:
            invalid_fields.append("seller.vat_id")
        if self.payment_means_type_code == "58":
            if self.payee_iban is None:
                invalid_fields.append("payee_iban")
            if self.payee_bic is None:
                invalid_fields.append("payee_bic")

        line_total = _money(sum((line.line_total for line in self.lines), Decimal("0.00")))
        tax_total = _money(sum((tax.tax_amount for tax in self.taxes), Decimal("0.00")))
        grand_total = _money(line_total + tax_total)
        expected_totals = {
            "totals.line_total": line_total,
            "totals.tax_basis_total": line_total,
            "totals.tax_total": tax_total,
            "totals.grand_total": grand_total,
            "totals.due_amount": grand_total,
        }
        for field_name, expected in expected_totals.items():
            actual = getattr(self.totals, field_name.rsplit(".", 1)[1])
            if _money(actual) != expected:
                invalid_fields.append(field_name)

        if invalid_fields:
            raise InvoiceSnapshotError(self.object_id, invalid_fields)
        return self


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _valid_tax_category(rate: Decimal, category_code: TaxCategoryCode) -> bool:
    normalized_rate = _money(rate)
    if normalized_rate == Decimal("0.00"):
        return category_code in {"Z", "AE", "G"}
    return category_code == "S"


def validate_invoice_snapshot(payload: object) -> InvoiceSnapshot:
    """Validate untrusted input while exposing only object IDs and field names."""
    try:
        return InvoiceSnapshot.model_validate(payload)
    except ValidationError as exc:
        source = payload if isinstance(payload, dict) else {}
        object_id = source.get("object_id", 0)
        safe_object_id = object_id if isinstance(object_id, int) else 0
        fields: list[str] = []
        for error in exc.errors(include_input=False):
            nested_error = error.get("ctx", {}).get("error")
            if isinstance(nested_error, InvoiceSnapshotError):
                fields.extend(nested_error.fields)
            else:
                fields.append(".".join(str(part) for part in error["loc"]))
        raise InvoiceSnapshotError(safe_object_id, fields) from None
