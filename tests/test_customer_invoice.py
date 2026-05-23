"""Tests for customer-invoice command (CMXUMS / collmex-cli-rg8)."""

from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from collmex_cli.api import CollmexError, extract_new_object_id, find_new_object_id
from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import AccountingDocument, CustomerInvoice, OpenItem

runner = CliRunner()


class TestExtractNewObjectId:
    """AC1/AC3: extract_new_object_id parses the Collmex NEW_OBJECT_ID record.

    The Collmex CSV convention is row[0] = record type, row[1] = first data
    field. The NEW_OBJECT_ID record format is ``NEW_OBJECT_ID;<id>``, so the
    booking number lives at row[1].
    """

    def test_returns_booking_number(self):
        """A real-shaped NEW_OBJECT_ID row yields the integer booking number."""
        assert extract_new_object_id([["NEW_OBJECT_ID", "12345"]]) == 12345

    def test_non_numeric_id_raises(self):
        """A non-numeric booking number raises CollmexError."""
        with pytest.raises(CollmexError, match="Invalid NEW_OBJECT_ID"):
            extract_new_object_id([["NEW_OBJECT_ID", "not-a-number"]])

    def test_missing_new_object_id_raises(self):
        """An empty response (no NEW_OBJECT_ID row) raises CollmexError."""
        with pytest.raises(CollmexError, match="did not include NEW_OBJECT_ID"):
            extract_new_object_id([])

    def test_find_returns_id_when_present(self):
        """find_new_object_id returns the booking number when the row is present."""
        assert find_new_object_id([["NEW_OBJECT_ID", "12345"]]) == 12345

    def test_find_returns_none_when_absent(self):
        """find_new_object_id returns None instead of raising when no id row exists."""
        assert find_new_object_id([["MESSAGE", "S", "204020", "OK"]]) is None

    @patch("collmex_cli.client.CollmexAPI")
    def test_create_customer_invoice_uses_parser(self, mock_api_cls):
        """create_customer_invoice runs the real parser over the API response."""
        mock_api = mock_api_cls.return_value
        mock_api.request.return_value = [["NEW_OBJECT_ID", "99999"]]

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api
        invoice = CustomerInvoice(
            customer_id=123,
            invoice_number="I2026_05_0001",
            invoice_date=date(2026, 5, 21),
            net_amount_full_tax=Decimal("100.00"),
            tax_full=Decimal("19.00"),
        )

        assert client.create_customer_invoice(invoice) == 99999


class TestVatCalculation:
    """AC4: VAT calculation and explicit tax handling for CMXUMS rows."""

    def test_vat_from_rate(self):
        """CMXUMS stores calculated VAT in field 7."""
        invoice = CustomerInvoice(
            customer_id=123,
            invoice_number="I2026_05_0001",
            invoice_date=date(2026, 5, 21),
            net_amount_full_tax=Decimal("100.00"),
            tax_full=Decimal("19.00"),
        )

        row = invoice.to_csv_row()

        assert row[0] == "CMXUMS"
        assert row[5] == "100,00"
        assert row[6] == "19,00"

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_explicit_tax_overrides_rate(self, mock_client_cls):
        """--tax is used directly instead of the --tax-rate calculation."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer_invoice.return_value = 12345

        result = runner.invoke(
            app,
            [
                "customer-invoice",
                "--customer-id",
                "123",
                "--invoice",
                "I2026_05_0002",
                "--date",
                "2026-05-21",
                "--net",
                "100.00",
                "--tax-rate",
                "19",
                "--tax",
                "18.50",
            ],
        )

        assert result.exit_code == 0
        invoice = instance.create_customer_invoice.call_args.args[0]
        assert invoice.tax_full == Decimal("18.50")


class TestCustomerInvoiceCommand:
    """AC1 and AC5: customer-invoice command integration."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_books_receivable(self, mock_client_cls):
        """customer-invoice sends a CMXUMS row that creates a receivable."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer_invoice.return_value = 12345

        result = runner.invoke(
            app,
            [
                "customer-invoice",
                "--customer-id",
                "123",
                "--invoice",
                "I2026_05_0001",
                "--date",
                "2026-05-21",
                "--net",
                "100.00",
                "--tax-rate",
                "19",
                "--text",
                "Consulting May",
            ],
        )

        assert result.exit_code == 0
        instance.create_customer_invoice.assert_called_once()
        invoice = instance.create_customer_invoice.call_args.args[0]
        row = invoice.to_csv_row()
        assert row[0] == "CMXUMS"
        assert row[1] == "123"
        assert row[4] == "I2026_05_0001"
        assert row[6] == "19,00"
        assert row[14] == ""
        assert row[18] == "8400"

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_buchungsnummer_in_json(self, mock_client_cls):
        """customer-invoice --json includes the Collmex booking number."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer_invoice.return_value = 12345

        result = runner.invoke(
            app,
            [
                "customer-invoice",
                "--customer-id",
                "123",
                "--invoice",
                "I2026_05_0001",
                "--date",
                "2026-05-21",
                "--net",
                "100.00",
                "--json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["buchungsnummer"] == 12345

    @patch("collmex_cli.client.CollmexAPI")
    def test_success_message_without_new_object_id_returns_none(self, mock_api_cls):
        """A CMXUMS success confirms with MESSAGE only and yields None, not an error.

        Regression for collmex-cli-30p: the booking succeeds but Collmex returns
        no NEW_OBJECT_ID, so create_customer_invoice must not raise.
        """
        mock_api = mock_api_cls.return_value
        mock_api.request.return_value = [
            ["MESSAGE", "S", "204020", "Datenübertragung erfolgreich. Es wurden 1 Datensätze verarbeitet."]
        ]

        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api
        invoice = CustomerInvoice(
            customer_id=123,
            invoice_number="I2026_05_0001",
            invoice_date=date(2026, 5, 21),
            net_amount_full_tax=Decimal("100.00"),
            tax_full=Decimal("19.00"),
        )

        assert client.create_customer_invoice(invoice) is None

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_duplicate_number_rejected(self, mock_client_cls):
        """Collmex errors, such as invalid customers, are shown clearly."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.create_customer_invoice.side_effect = CollmexError(
            "Invalid customer ID or duplicate invoice conflict"
        )

        result = runner.invoke(
            app,
            [
                "customer-invoice",
                "--customer-id",
                "999999",
                "--invoice",
                "I2026_05_0001",
                "--date",
                "2026-05-21",
                "--net",
                "100.00",
            ],
        )

        assert result.exit_code == 1
        assert "Collmex API error" in result.output
        assert "Invalid customer ID" in result.output


class TestOpenItems:
    """AC2: customer open items display imported invoice numbers."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_appears_in_open_items(self, mock_client_cls):
        """open-items --customer lists the mocked customer open item."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_open_items.return_value = [
            OpenItem(
                customer_id=123,
                customer_name="Example GmbH",
                invoice_number="I2026_05_0001",
                document_date=date(2026, 5, 21),
                due_date=date(2026, 6, 20),
                open_amount=Decimal("119.00"),
            )
        ]

        result = runner.invoke(app, ["open-items", "--customer", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["invoice_number"] == "I2026_05_0001"
        assert data[0]["customer_name"] == "Example GmbH"
        instance.get_open_items.assert_called_once_with(
            vendor=False,
            vendor_id=None,
            customer_id=None,
        )


class TestBookings:
    """AC3: bookings display receivable and revenue account lines."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_appears_in_bookings(self, mock_client_cls):
        """bookings --from X --to Y lists debtor and revenue accounts."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_bookings.return_value = [
            AccountingDocument(
                booking_id=7001,
                document_date=date(2026, 5, 21),
                account_number=1400,
                debit_credit="S",
                amount=Decimal("119.00"),
                booking_text="I2026_05_0001 Consulting May",
                customer_id=123,
                invoice_number="I2026_05_0001",
            ),
            AccountingDocument(
                booking_id=7001,
                document_date=date(2026, 5, 21),
                account_number=8400,
                debit_credit="H",
                amount=Decimal("100.00"),
                booking_text="I2026_05_0001 Consulting May",
                customer_id=123,
                invoice_number="I2026_05_0001",
            ),
        ]

        result = runner.invoke(
            app,
            ["bookings", "--from", "2026-05-01", "--to", "2026-05-31"],
        )

        assert result.exit_code == 0
        assert "1400" in result.output
        assert "8400" in result.output
        assert "I2026_05_0001" in result.output
        instance.get_bookings.assert_called_once_with(
            fiscal_year=None,
            account_number=None,
            vendor_id=None,
            customer_id=None,
            text=None,
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 31),
        )
