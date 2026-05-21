"""Tests for customer-invoice command (CMXUMS / collmex-cli-rg8)."""

from decimal import Decimal

from collmex_cli.models import CustomerInvoice


class TestVatCalculation:
    """AC4: VAT calculation and explicit tax handling for CMXUMS rows."""

    def test_vat_from_rate(self):
        """CMXUMS stores calculated VAT in field 7."""
        invoice = CustomerInvoice(
            customer_id=123,
            invoice_number="I2026_05_0001",
            invoice_date="2026-05-21",
            net_amount_full_tax=Decimal("100.00"),
            tax_full=Decimal("19.00"),
        )

        row = invoice.to_csv_row()

        assert row[0] == "CMXUMS"
        assert row[5] == "100.00"
        assert row[6] == "19.00"
