"""Tests for INVOICE_PAYMENT_GET support.

Covers:
- InvoicePayment Pydantic model
- CollmexClient.get_invoice_payments()
- Filter parameters
- CLI command 'invoice-payments'

Real API response layout (verified against live Collmex API):
  0: INVOICE_PAYMENT
  1: invoice_number
  2: payment_date (YYYYMMDD)
  3: payment_amount (German decimal, e.g. "195,05")
  4: invoice_amount (total invoice amount)
  5: fiscal_year
  6: booking_id
  7: payment_type code
  8: (unused / empty)
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import InvoicePayment

runner = CliRunner()


# =============================================================================
# Helpers
# =============================================================================


def _make_payment_row(
    invoice_number: str = "RE-2026-001",
    payment_date: str = "20260115",
    payment_amount: str = "1190,00",
    invoice_amount: str = "1190,00",
    fiscal_year: str = "2026",
    booking_id: str = "5001",
    payment_type: str = "2",
) -> list[str]:
    """Build a raw CSV row as returned by the real Collmex API."""
    return [
        "INVOICE_PAYMENT",
        invoice_number,
        payment_date,
        payment_amount,
        invoice_amount,
        fiscal_year,
        booking_id,
        payment_type,
        "",
    ]


def _make_payment(**kwargs) -> InvoicePayment:
    """Create an InvoicePayment with sensible defaults."""
    defaults = dict(
        record_type="INVOICE_PAYMENT",
        invoice_number="RE-2026-001",
        payment_date=date(2026, 1, 15),
        payment_amount=Decimal("1190.00"),
        invoice_amount=Decimal("1190.00"),
        fiscal_year=2026,
        booking_id=5001,
        payment_type="2",
    )
    defaults.update(kwargs)
    return InvoicePayment(**defaults)


# =============================================================================
# TestInvoicePaymentModel
# =============================================================================


class TestInvoicePaymentModel:
    """Tests for the InvoicePayment Pydantic model."""

    def test_from_csv_row_basic(self):
        """from_csv_row parses all fields correctly."""
        row = _make_payment_row()
        payment = InvoicePayment.from_csv_row(row)

        assert payment.record_type == "INVOICE_PAYMENT"
        assert payment.invoice_number == "RE-2026-001"
        assert payment.payment_date == date(2026, 1, 15)
        assert payment.payment_amount == Decimal("1190.00")
        assert payment.invoice_amount == Decimal("1190.00")
        assert payment.fiscal_year == 2026
        assert payment.booking_id == 5001
        assert payment.payment_type == "2"

    def test_from_csv_row_german_decimal(self):
        """German comma decimal separator is parsed correctly."""
        row = _make_payment_row(payment_amount="2499,99", invoice_amount="2499,99")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_amount == Decimal("2499.99")
        assert payment.invoice_amount == Decimal("2499.99")

    def test_from_csv_row_partial_payment(self):
        """Partial payment: payment_amount differs from invoice_amount."""
        row = _make_payment_row(payment_amount="195,05", invoice_amount="35,49")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_amount == Decimal("195.05")
        assert payment.invoice_amount == Decimal("35.49")

    def test_from_csv_row_zero_amount(self):
        """Zero amount parses correctly."""
        row = _make_payment_row(payment_amount="0,00")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_amount == Decimal("0.00")

    def test_from_csv_row_date_validation(self):
        """payment_date field_validator accepts YYYYMMDD string."""
        row = _make_payment_row(payment_date="20261231")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_date == date(2026, 12, 31)

    def test_from_csv_row_empty_date(self):
        """Empty payment_date results in None."""
        row = _make_payment_row(payment_date="")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_date is None

    def test_from_csv_row_empty_amount(self):
        """Empty payment_amount results in None."""
        row = _make_payment_row(payment_amount="")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_amount is None

    def test_from_csv_row_strips_invoice_number(self):
        """Leading/trailing whitespace in invoice_number is stripped."""
        row = _make_payment_row(invoice_number=" 10-04610-56733")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.invoice_number == "10-04610-56733"

    def test_field_validator_accepts_date_object(self):
        """field_validator accepts date objects directly (model construction)."""
        payment = _make_payment(payment_date=date(2026, 6, 1))
        assert payment.payment_date == date(2026, 6, 1)

    def test_model_dump_serialization(self):
        """model_dump() returns a dict with correct types."""
        payment = _make_payment()
        data = payment.model_dump()
        assert data["invoice_number"] == "RE-2026-001"
        assert data["payment_date"] == date(2026, 1, 15)
        assert isinstance(data["payment_amount"], Decimal)
        assert data["fiscal_year"] == 2026

    def test_record_type_in_record_types_dict(self):
        """INVOICE_PAYMENT is registered in RECORD_TYPES."""
        from collmex_cli.models import RECORD_TYPES
        assert "INVOICE_PAYMENT" in RECORD_TYPES
        assert RECORD_TYPES["INVOICE_PAYMENT"] is InvoicePayment

    def test_from_csv_row_short_row_uses_defaults(self):
        """Short CSV row (missing trailing fields) doesn't raise."""
        row = ["INVOICE_PAYMENT", "RE-001"]
        payment = InvoicePayment.from_csv_row(row)
        assert payment.invoice_number == "RE-001"
        assert payment.payment_date is None
        assert payment.payment_amount is None
        assert payment.booking_id is None


# =============================================================================
# TestGetInvoicePayments
# =============================================================================


class TestGetInvoicePayments:
    """Tests for CollmexClient.get_invoice_payments()."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_returns_invoice_payments(self, mock_api_cls):
        """Returns list of InvoicePayment objects from API response."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            _make_payment_row(),
            _make_payment_row(invoice_number="RE-2026-002", booking_id="5002"),
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        payments = client.get_invoice_payments()

        assert len(payments) == 2
        assert all(isinstance(p, InvoicePayment) for p in payments)
        assert payments[0].invoice_number == "RE-2026-001"
        assert payments[1].invoice_number == "RE-2026-002"

    @patch("collmex_cli.client.CollmexAPI")
    def test_filters_non_payment_rows(self, mock_api_cls):
        """Rows with record type != INVOICE_PAYMENT are filtered out."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            ["MESSAGE", "0", "Keine Daten"],
            _make_payment_row(),
        ]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        payments = client.get_invoice_payments()
        assert len(payments) == 1

    @patch("collmex_cli.client.CollmexAPI")
    def test_empty_response(self, mock_api_cls):
        """Empty API response returns empty list."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        payments = client.get_invoice_payments()
        assert payments == []

    @patch("collmex_cli.client.CollmexAPI")
    def test_request_row_structure(self, mock_api_cls):
        """API request row has correct structure (INVOICE_PAYMENT_GET)."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments()

        call_args = mock_api.request.call_args[0][0]
        assert call_args[0] == "INVOICE_PAYMENT_GET"
        assert call_args[1] == "1"  # company_id

    @patch("collmex_cli.client.CollmexAPI")
    def test_handles_none_rows(self, mock_api_cls):
        """None entries in API response are skipped."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [None, _make_payment_row()]
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        payments = client.get_invoice_payments()
        assert len(payments) == 1


# =============================================================================
# TestInvoicePaymentsFilters
# =============================================================================


class TestInvoicePaymentsFilters:
    """Tests for filter parameters in get_invoice_payments()."""

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_invoice_number(self, mock_api_cls):
        """invoice_number filter is passed to API request row."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(invoice_number="RE-2026-042")

        row = mock_api.request.call_args[0][0]
        assert "RE-2026-042" in row

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_customer_id(self, mock_api_cls):
        """customer_id filter is passed to API request row."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(customer_id=10042)

        row = mock_api.request.call_args[0][0]
        assert "10042" in row

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_date_from(self, mock_api_cls):
        """date_from filter is passed in YYYYMMDD format."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(date_from=date(2026, 1, 1))

        row = mock_api.request.call_args[0][0]
        assert "20260101" in row

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_date_to(self, mock_api_cls):
        """date_to filter is passed in YYYYMMDD format."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(date_to=date(2026, 12, 31))

        row = mock_api.request.call_args[0][0]
        assert "20261231" in row

    @patch("collmex_cli.client.CollmexAPI")
    def test_no_filters_uses_empty_strings(self, mock_api_cls):
        """Without filters, optional fields are empty strings in the request."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments()

        row = mock_api.request.call_args[0][0]
        # Fields 2-5 should be empty strings when no filter given
        assert row[2] == ""  # invoice_number
        assert row[3] == ""  # customer_id
        assert row[4] == ""  # date_from
        assert row[5] == ""  # date_to


# =============================================================================
# TestInvoicePaymentsCLI
# =============================================================================


class TestInvoicePaymentsCLI:
    """Tests for the 'invoice-payments' CLI command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_table_output_default(self, mock_client_cls):
        """Default output shows a Rich table with payment data."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = [
            _make_payment(),
        ]

        result = runner.invoke(app, ["invoice-payments"])

        assert result.exit_code == 0
        assert "RE-2026" in result.output
        assert "1190" in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_json_output(self, mock_client_cls):
        """--json flag outputs valid JSON array."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = [
            _make_payment(),
        ]

        result = runner.invoke(app, ["invoice-payments", "--json"])

        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["invoice_number"] == "RE-2026-001"
        assert data[0]["payment_date"] == "2026-01-15"
        assert data[0]["payment_amount"] == "1190.00"
        assert data[0]["fiscal_year"] == 2026

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_filter_invoice_number_passed_to_client(self, mock_client_cls):
        """--invoice-number option is forwarded to get_invoice_payments()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(app, ["invoice-payments", "--invoice-number", "RE-2026-042"])

        assert result.exit_code == 0
        instance.get_invoice_payments.assert_called_once_with(
            invoice_number="RE-2026-042",
            customer_id=None,
            date_from=None,
            date_to=None,
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_filter_customer_id_passed_to_client(self, mock_client_cls):
        """--customer-id option is forwarded to get_invoice_payments()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(app, ["invoice-payments", "--customer-id", "10042"])

        assert result.exit_code == 0
        instance.get_invoice_payments.assert_called_once_with(
            invoice_number=None,
            customer_id=10042,
            date_from=None,
            date_to=None,
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_empty_result_shows_table(self, mock_client_cls):
        """Empty result still shows table (no crash)."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(app, ["invoice-payments"])

        assert result.exit_code == 0

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_multiple_payments_in_table(self, mock_client_cls):
        """Multiple payments are all shown in the table."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = [
            _make_payment(invoice_number="RE-001", payment_amount=Decimal("100.00")),
            _make_payment(invoice_number="RE-002", payment_amount=Decimal("200.00")),
        ]

        result = runner.invoke(app, ["invoice-payments"])

        assert result.exit_code == 0
        assert "RE-001" in result.output
        assert "RE-002" in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_date_filters_passed_to_client(self, mock_client_cls):
        """--date-from and --date-to are parsed and forwarded."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(
            app,
            ["invoice-payments", "--date-from", "2026-01-01", "--date-to", "2026-03-31"],
        )

        assert result.exit_code == 0
        instance.get_invoice_payments.assert_called_once_with(
            invoice_number=None,
            customer_id=None,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 3, 31),
        )
