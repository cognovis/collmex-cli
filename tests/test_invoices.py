"""Tests for INVOICE_GET: models, client method, CLI command, and filters."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from collmex_cli.client import CollmexClient
from collmex_cli.main import app
from collmex_cli.models import Invoice, InvoiceLine

runner = CliRunner()


# =============================================================================
# Helpers
# =============================================================================

def _make_header_row(
    invoice_id: int = 1001,
    customer_id: int = 42,
    customer_company: str = "Acme GmbH",
    invoice_date: str = "20260115",
    due_date: str = "20260215",
    currency: str = "EUR",
    total_net: str = "100,00",
    total_vat: str = "19,00",
    total_gross: str = "119,00",
    cancelled: int = 0,
    invoice_number_text: str = "RE-2026-001",
) -> list[str]:
    """Build a minimal CMXINV header row (position=0)."""
    # 58+ fields, most empty
    row = [""] * 60
    row[0] = "CMXINV"
    row[1] = str(invoice_id)
    row[2] = "0"  # header
    row[3] = "0"  # invoice_type = Rechnung
    row[4] = str(customer_id)
    row[5] = ""   # salutation
    row[6] = ""   # title
    row[7] = customer_company
    row[8] = ""   # first name
    row[9] = ""   # last name
    row[18] = invoice_date
    row[26] = currency
    row[31] = due_date
    row[50] = total_net
    row[51] = total_vat
    row[52] = total_gross
    row[56] = str(cancelled)
    row[57] = invoice_number_text
    return row


def _make_line_row(
    invoice_id: int = 1001,
    position: int = 1,
    text: str = "Beratungsleistung",
    quantity: str = "2,00",
    unit: str = "Std",
    price: str = "50,00",
    vat_rate: str = "19,00",
    product_id: str = "BERAT",
    total_net: str = "100,00",
    total_vat: str = "19,00",
    total_gross: str = "119,00",
) -> list[str]:
    """Build a minimal CMXINV line item row (position>0)."""
    row = [""] * 60
    row[0] = "CMXINV"
    row[1] = str(invoice_id)
    row[2] = str(position)
    row[33] = text
    row[34] = quantity
    row[35] = unit
    row[36] = price
    row[37] = "1"  # price_type = net
    row[38] = vat_rate
    row[39] = product_id
    row[50] = total_net
    row[51] = total_vat
    row[52] = total_gross
    return row


# =============================================================================
# Model tests
# =============================================================================


class TestInvoiceModel:
    """Tests for Invoice.from_cmxinv_rows()."""

    def test_invoice_get(self):
        """A header row produces one Invoice with correct fields."""
        rows = [_make_header_row()]
        invoices = Invoice.from_cmxinv_rows(rows)

        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.invoice_id == 1001
        assert inv.customer_id == 42
        assert inv.customer_company == "Acme GmbH"
        assert inv.invoice_date == date(2026, 1, 15)
        assert inv.due_date == date(2026, 2, 15)
        assert inv.currency == "EUR"
        assert inv.total_net == Decimal("100.00")
        assert inv.total_vat == Decimal("19.00")
        assert inv.total_gross == Decimal("119.00")
        assert inv.cancelled == 0
        assert inv.invoice_number_text == "RE-2026-001"
        assert inv.lines == []

    def test_invoice_lines(self):
        """Multi-line invoice: header + 2 lines grouped under one Invoice."""
        rows = [
            _make_header_row(invoice_id=2001),
            _make_line_row(invoice_id=2001, position=1, text="Service A"),
            _make_line_row(invoice_id=2001, position=2, text="Service B", price="75,00"),
        ]
        invoices = Invoice.from_cmxinv_rows(rows)

        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.invoice_id == 2001
        assert len(inv.lines) == 2

        line1 = inv.lines[0]
        assert line1.position == 1
        assert line1.text == "Service A"
        assert line1.quantity == Decimal("2.00")
        assert line1.unit == "Std"
        assert line1.vat_rate == Decimal("19.00")
        assert line1.product_id == "BERAT"

        line2 = inv.lines[1]
        assert line2.position == 2
        assert line2.text == "Service B"
        assert line2.price == Decimal("75.00")

    def test_multiple_invoices_grouped_separately(self):
        """Rows from two different invoices produce two Invoice objects."""
        rows = [
            _make_header_row(invoice_id=3001),
            _make_line_row(invoice_id=3001, position=1),
            _make_header_row(invoice_id=3002, customer_company="Beta AG"),
            _make_line_row(invoice_id=3002, position=1),
        ]
        invoices = Invoice.from_cmxinv_rows(rows)

        assert len(invoices) == 2
        ids = {inv.invoice_id for inv in invoices}
        assert ids == {3001, 3002}

    def test_non_cmxinv_rows_ignored(self):
        """Rows that are not CMXINV are silently ignored."""
        rows = [
            ["MESSAGE", "0", "Erfolgreich"],
            _make_header_row(invoice_id=4001),
        ]
        invoices = Invoice.from_cmxinv_rows(rows)
        assert len(invoices) == 1

    def test_empty_rows(self):
        """Empty input returns empty list."""
        assert Invoice.from_cmxinv_rows([]) == []


# =============================================================================
# Client method tests
# =============================================================================


class TestGetInvoices:
    """Tests for CollmexClient.get_invoices()."""

    def _make_client(self, mock_api):
        """Create a CollmexClient with a mock API."""
        client = CollmexClient.__new__(CollmexClient)
        client.api = mock_api
        return client

    def test_invoice_get_builds_correct_row(self):
        """get_invoices() sends INVOICE_GET row with correct format."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        client = self._make_client(mock_api)

        client.get_invoices()

        mock_api.request.assert_called_once()
        sent_row = mock_api.request.call_args[0][0]
        assert sent_row[0] == "INVOICE_GET"
        assert sent_row[1] == "1"  # company_id

    def test_invoice_get_returns_invoice_list(self):
        """get_invoices() returns parsed Invoice objects."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = [
            _make_header_row(invoice_id=5001),
            _make_line_row(invoice_id=5001, position=1),
        ]
        client = self._make_client(mock_api)

        invoices = client.get_invoices()

        assert len(invoices) == 1
        assert isinstance(invoices[0], Invoice)
        assert invoices[0].invoice_id == 5001
        assert len(invoices[0].lines) == 1

    def test_invoice_filters_invoice_id(self):
        """invoice_id filter is passed at position 2 of the request row."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        client = self._make_client(mock_api)

        client.get_invoices(invoice_id=1234)

        sent_row = mock_api.request.call_args[0][0]
        assert sent_row[2] == "1234"

    def test_invoice_filters_customer_id(self):
        """customer_id filter is passed at position 3 of the request row."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        client = self._make_client(mock_api)

        client.get_invoices(customer_id=99)

        sent_row = mock_api.request.call_args[0][0]
        assert sent_row[3] == "99"

    def test_invoice_filters_date_from(self):
        """date_from filter is formatted as YYYYMMDD at position 4."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        client = self._make_client(mock_api)

        client.get_invoices(date_from=date(2026, 1, 1))

        sent_row = mock_api.request.call_args[0][0]
        assert sent_row[4] == "20260101"

    def test_invoice_filters_date_to(self):
        """date_to filter is formatted as YYYYMMDD at position 5."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        client = self._make_client(mock_api)

        client.get_invoices(date_to=date(2026, 3, 31))

        sent_row = mock_api.request.call_args[0][0]
        assert sent_row[5] == "20260331"

    def test_empty_filters_produce_empty_strings(self):
        """Without filters, all filter positions are empty strings."""
        mock_api = MagicMock()
        mock_api.config.company_id = 1
        mock_api.request.return_value = []
        client = self._make_client(mock_api)

        client.get_invoices()

        sent_row = mock_api.request.call_args[0][0]
        assert sent_row[2] == ""  # invoice_id
        assert sent_row[3] == ""  # customer_id
        assert sent_row[4] == ""  # date_from
        assert sent_row[5] == ""  # date_to


# =============================================================================
# CLI tests
# =============================================================================


class TestInvoicesCli:
    """Tests for the CLI 'invoices' command."""

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_invoices_cli_table(self, mock_client_cls):
        """Table output lists invoice columns."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoices.return_value = [
            Invoice(
                invoice_id=6001,
                customer_company="Test GmbH",
                invoice_date=date(2026, 2, 1),
                total_net=Decimal("200.00"),
                total_gross=Decimal("238.00"),
                currency="EUR",
                invoice_number_text="RE-2026-100",
            )
        ]

        result = runner.invoke(app, ["invoices"])

        assert result.exit_code == 0
        assert "RE-2026-100" in result.output
        assert "Test GmbH" in result.output
        assert "200" in result.output

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_invoices_cli_json(self, mock_client_cls):
        """JSON output contains full invoice data."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoices.return_value = [
            Invoice(
                invoice_id=6002,
                customer_company="Beta AG",
                invoice_date=date(2026, 2, 15),
                total_net=Decimal("500.00"),
                total_gross=Decimal("595.00"),
                currency="EUR",
                invoice_number_text="RE-2026-200",
                lines=[
                    InvoiceLine(
                        position=1,
                        text="Development",
                        quantity=Decimal("10"),
                        unit="h",
                        price=Decimal("50.00"),
                        total_gross=Decimal("595.00"),
                    )
                ],
            )
        ]

        result = runner.invoke(app, ["invoices", "--json"])

        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["invoice_id"] == 6002
        assert data[0]["customer_company"] == "Beta AG"
        assert data[0]["invoice_number_text"] == "RE-2026-200"
        assert len(data[0]["lines"]) == 1
        assert data[0]["lines"][0]["text"] == "Development"

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_invoices_cli_customer_id_filter(self, mock_client_cls):
        """--customer-id is forwarded to get_invoices()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoices.return_value = []

        result = runner.invoke(app, ["invoices", "--customer-id", "77"])

        assert result.exit_code == 0
        instance.get_invoices.assert_called_once_with(
            invoice_id=None,
            customer_id=77,
            date_from=None,
            date_to=None,
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_invoices_cli_invoice_id_filter(self, mock_client_cls):
        """--invoice-id is forwarded to get_invoices()."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoices.return_value = []

        result = runner.invoke(app, ["invoices", "--invoice-id", "9999"])

        assert result.exit_code == 0
        instance.get_invoices.assert_called_once_with(
            invoice_id=9999,
            customer_id=None,
            date_from=None,
            date_to=None,
        )

    @patch("collmex_cli.main.CollmexClient", autospec=True)
    def test_invoices_cli_date_filters(self, mock_client_cls):
        """--from and --to are parsed and forwarded."""
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.get_invoices.return_value = []

        result = runner.invoke(app, ["invoices", "--from", "2026-01-01", "--to", "2026-03-31"])

        assert result.exit_code == 0
        instance.get_invoices.assert_called_once_with(
            invoice_id=None,
            customer_id=None,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 3, 31),
        )
