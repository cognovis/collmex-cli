"""Tests for INVOICE_PAYMENT_GET support.

Covers:
- InvoicePayment Pydantic model
- CollmexClient.get_invoice_payments()
- Filter parameters
- CLI command 'invoice-payments'

Official API field layout (source: https://www.collmex.de/handbuch_buchhaltung_pro.html#api):
  1: Satzart           — INVOICE_PAYMENT
  2: Rechnungsnummer   — Invoice number
  3: Datum             — Payment date (YYYYMMDD)
  4: Gezahlter Betrag  — Actually paid via bank/cash
  5: Reduzierender Betrag — Open item reduced by this amount (may differ: Skonto etc.)
  6: Geschäftsjahr     — Fiscal year of the booking
  7: BuchungNr         — Booking number
  8: BuchungPos        — Booking position
  9: Systemname        — External system name

Key: Geschäftsjahr + BuchungNr + BuchungPos uniquely identify a payment.
When a payment is reversed, Datum and Betrag are empty.

Query fields (INVOICE_PAYMENT_GET):
  2: Firma Nr
  3: Rechnungsnummer (optional)
  4: Nur neue Zahlungen (1 = only new)
  5: Systemname
  No customer_id filter exists in this API.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
    reducing_amount: str = "1190,00",
    fiscal_year: str = "2026",
    booking_id: str = "5001",
    booking_position: str = "2",
    system_name: str = "",
) -> list[str]:
    """Build a raw CSV row matching the official Collmex INVOICE_PAYMENT spec."""
    return [
        "INVOICE_PAYMENT",  # [0] Satzart
        invoice_number,     # [1] Rechnungsnummer
        payment_date,       # [2] Datum
        payment_amount,     # [3] Gezahlter Betrag
        reducing_amount,    # [4] Reduzierender Betrag
        fiscal_year,        # [5] Geschäftsjahr
        booking_id,         # [6] BuchungNr
        booking_position,   # [7] BuchungPos
        system_name,        # [8] Systemname
    ]


def _make_payment(**kwargs) -> InvoicePayment:
    """Create an InvoicePayment with sensible defaults."""
    defaults = dict(
        record_type="INVOICE_PAYMENT",
        invoice_number="RE-2026-001",
        payment_date=date(2026, 1, 15),
        payment_amount=Decimal("1190.00"),
        reducing_amount=Decimal("1190.00"),
        fiscal_year=2026,
        booking_id=5001,
        booking_position=2,
        system_name="",
    )
    defaults.update(kwargs)
    return InvoicePayment(**defaults)


# =============================================================================
# TestInvoicePaymentModel
# =============================================================================


class TestInvoicePaymentModel:
    """Tests for the InvoicePayment Pydantic model."""

    def test_from_csv_row_basic(self):
        """from_csv_row parses all fields per official API spec."""
        row = _make_payment_row()
        payment = InvoicePayment.from_csv_row(row)

        assert payment.record_type == "INVOICE_PAYMENT"
        assert payment.invoice_number == "RE-2026-001"
        assert payment.payment_date == date(2026, 1, 15)
        assert payment.payment_amount == Decimal("1190.00")
        assert payment.reducing_amount == Decimal("1190.00")
        assert payment.fiscal_year == 2026
        assert payment.booking_id == 5001
        assert payment.booking_position == 2
        assert payment.system_name == ""

    def test_from_csv_row_german_decimal(self):
        """German comma decimal separator is parsed correctly."""
        row = _make_payment_row(payment_amount="2499,99", reducing_amount="2500,00")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_amount == Decimal("2499.99")
        assert payment.reducing_amount == Decimal("2500.00")

    def test_from_csv_row_skonto_difference(self):
        """Paid amount can differ from reducing amount (e.g. Skonto)."""
        row = _make_payment_row(payment_amount="195,05", reducing_amount="200,00")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_amount == Decimal("195.05")
        assert payment.reducing_amount == Decimal("200.00")

    def test_from_csv_row_reversed_payment_empty_date(self):
        """Reversed payment: date and amount are empty."""
        row = _make_payment_row(payment_date="", payment_amount="")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_date is None
        assert payment.payment_amount is None

    def test_from_csv_row_date_format(self):
        """Payment date YYYYMMDD is parsed to date object."""
        row = _make_payment_row(payment_date="20261231")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.payment_date == date(2026, 12, 31)

    def test_from_csv_row_booking_position(self):
        """BuchungPos (field 8) is parsed correctly."""
        row = _make_payment_row(booking_position="7")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.booking_position == 7

    def test_from_csv_row_system_name(self):
        """Systemname (field 9) is parsed correctly."""
        row = _make_payment_row(system_name="Kasse1")
        payment = InvoicePayment.from_csv_row(row)
        assert payment.system_name == "Kasse1"

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
        """model_dump() returns a dict with all official fields."""
        payment = _make_payment()
        data = payment.model_dump()
        assert data["invoice_number"] == "RE-2026-001"
        assert data["payment_date"] == date(2026, 1, 15)
        assert isinstance(data["payment_amount"], Decimal)
        assert isinstance(data["reducing_amount"], Decimal)
        assert data["fiscal_year"] == 2026
        assert data["booking_id"] == 5001
        assert data["booking_position"] == 2

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
        assert payment.booking_position is None


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
        """API request row matches official INVOICE_PAYMENT_GET field order."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments()

        row = mock_api.request.call_args[0][0]
        assert row[0] == "INVOICE_PAYMENT_GET"
        assert row[1] == "1"   # Firma Nr
        assert row[2] == ""    # Rechnungsnummer (empty = all)
        assert row[3] == ""    # Nur neue Zahlungen (empty = all)
        assert row[4] == ""    # Systemname

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
    """Tests for filter parameters in get_invoice_payments().

    Official INVOICE_PAYMENT_GET filters:
    - invoice_number (Rechnungsnummer)
    - only_new (Nur neue Zahlungen)
    - system_name (Systemname)
    Note: No customer_id or date filter exists in this API.
    """

    @patch("collmex_cli.client.CollmexAPI")
    def test_filter_by_invoice_number(self, mock_api_cls):
        """invoice_number is passed as field 3 of INVOICE_PAYMENT_GET."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(invoice_number="RE-2026-042")

        row = mock_api.request.call_args[0][0]
        assert row[2] == "RE-2026-042"

    @patch("collmex_cli.client.CollmexAPI")
    def test_only_new_flag(self, mock_api_cls):
        """only_new=True sets field 4 to '1'."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(only_new=True)

        row = mock_api.request.call_args[0][0]
        assert row[3] == "1"

    @patch("collmex_cli.client.CollmexAPI")
    def test_system_name(self, mock_api_cls):
        """system_name is passed as field 5."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(system_name="Kasse1")

        row = mock_api.request.call_args[0][0]
        assert row[4] == "Kasse1"

    @patch("collmex_cli.client.CollmexAPI")
    def test_no_filters_all_empty(self, mock_api_cls):
        """Without filters, optional fields are empty strings."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments()

        row = mock_api.request.call_args[0][0]
        assert row[2] == ""  # Rechnungsnummer
        assert row[3] == ""  # Nur neue Zahlungen
        assert row[4] == ""  # Systemname

    @patch("collmex_cli.client.CollmexAPI")
    def test_only_new_false_is_empty(self, mock_api_cls):
        """only_new=False sends empty string (not '0')."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        mock_api_cls.return_value = mock_api

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api

        client.get_invoice_payments(only_new=False)

        row = mock_api.request.call_args[0][0]
        assert row[3] == ""


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
        """--json flag outputs valid JSON with all official fields."""
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
        assert data[0]["reducing_amount"] == "1190.00"
        assert data[0]["fiscal_year"] == 2026
        assert data[0]["booking_id"] == 5001
        assert data[0]["booking_position"] == 2

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_filter_invoice_number_passed_to_client(self, mock_client_cls):
        """--invoice-number is forwarded to get_invoice_payments()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(app, ["invoice-payments", "--invoice-number", "RE-2026-042"])

        assert result.exit_code == 0
        instance.get_invoice_payments.assert_called_once_with(
            invoice_number="RE-2026-042",
            only_new=False,
            system_name=None,
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_only_new_flag(self, mock_client_cls):
        """--only-new flag is forwarded to get_invoice_payments()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(app, ["invoice-payments", "--only-new"])

        assert result.exit_code == 0
        instance.get_invoice_payments.assert_called_once_with(
            invoice_number=None,
            only_new=True,
            system_name=None,
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_empty_result_shows_table(self, mock_client_cls):
        """Empty result still renders without crash."""
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
    def test_system_name_passed_to_client(self, mock_client_cls):
        """--system is forwarded to get_invoice_payments()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoice_payments.return_value = []

        result = runner.invoke(app, ["invoice-payments", "--system", "Kasse1"])

        assert result.exit_code == 0
        instance.get_invoice_payments.assert_called_once_with(
            invoice_number=None,
            only_new=False,
            system_name="Kasse1",
        )
