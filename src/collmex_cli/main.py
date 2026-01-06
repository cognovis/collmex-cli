"""Collmex CLI - LLM-friendly wrapper for Collmex accounting API."""

import json
import sys
from datetime import date
from decimal import Decimal
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import __version__
from .api import CollmexAuthError, CollmexError
from .client import CollmexClient
from .models import Vendor, VendorInvoice

app = typer.Typer(
    name="collmex",
    help="CLI for Collmex accounting API (Buchhaltung Pro)",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def json_serial(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def output_json(data: list | dict) -> None:
    """Output data as JSON (LLM-friendly format)."""
    print(json.dumps(data, default=json_serial, ensure_ascii=False, indent=2))


def output_table(title: str, columns: list[str], rows: list[list]) -> None:
    """Output data as a rich table."""
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(v) if v is not None else "" for v in row])
    console.print(table)


def handle_error(e: Exception) -> None:
    """Handle and display errors."""
    if isinstance(e, CollmexAuthError):
        err_console.print(f"[red]Authentication failed:[/red] {e}")
        err_console.print("Check your COLLMEX_* environment variables")
    elif isinstance(e, CollmexError):
        err_console.print(f"[red]Collmex API error:[/red] {e}")
    elif isinstance(e, ValidationError):
        err_console.print(f"[red]Configuration error:[/red] {e}")
        err_console.print("Ensure COLLMEX_CUSTOMER_ID, COLLMEX_USERNAME, COLLMEX_PASSWORD are set")
    else:
        err_console.print(f"[red]Error:[/red] {e}")
    raise typer.Exit(1)


# =============================================================================
# Vendors Commands
# =============================================================================


@app.command("vendors")
def list_vendors(
    vendor_id: Annotated[int | None, typer.Option("--id", help="Filter by vendor ID")] = None,
    search: Annotated[str | None, typer.Option("--search", "-s", help="Search text")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """List vendors (Lieferanten)."""
    try:
        with CollmexClient() as client:
            vendors = client.get_vendors(vendor_id=vendor_id, text=search)

        if json_output:
            output_json([v.model_dump() for v in vendors])
        else:
            rows = [
                [v.vendor_id, v.company_name or f"{v.first_name} {v.last_name}".strip(), v.city, v.email]
                for v in vendors
            ]
            output_table("Vendors", ["ID", "Name", "City", "Email"], rows)
            console.print(f"\n[dim]Total: {len(vendors)} vendors[/dim]")
    except Exception as e:
        handle_error(e)


@app.command("vendor-create")
def create_vendor(
    company_name: Annotated[str, typer.Option("--company", "-c", help="Company name")],
    street: Annotated[str | None, typer.Option("--street", help="Street address")] = None,
    postal_code: Annotated[str | None, typer.Option("--zip", help="Postal code")] = None,
    city: Annotated[str | None, typer.Option("--city", help="City")] = None,
    country: Annotated[str, typer.Option("--country", help="Country code")] = "DE",
    email: Annotated[str | None, typer.Option("--email", help="Email address")] = None,
    iban: Annotated[str | None, typer.Option("--iban", help="IBAN")] = None,
    vat_id: Annotated[str | None, typer.Option("--vat-id", help="VAT ID (USt-IdNr)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Create a new vendor (Lieferant)."""
    try:
        vendor = Vendor(
            company_name=company_name,
            street=street or "",
            postal_code=postal_code or "",
            city=city or "",
            country=country,
            email=email or "",
            iban=iban or "",
            vat_id=vat_id or "",
        )

        with CollmexClient() as client:
            result = client.create_vendor(vendor)

        if json_output:
            output_json({"status": "created", "response": result})
        else:
            console.print("[green]Vendor created successfully[/green]")
            console.print(f"Response: {result}")
    except Exception as e:
        handle_error(e)


@app.command("vendor-match")
def match_vendor(
    iban: Annotated[str | None, typer.Option("--iban", help="IBAN to match")] = None,
    vat_id: Annotated[str | None, typer.Option("--vat-id", help="VAT ID (USt-IdNr) to match")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Company name to match")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = True,
) -> None:
    """Match a vendor by IBAN, VAT ID, or name.

    Matching priority:
    1. IBAN (exact match)
    2. VAT ID (exact match)
    3. Name (fuzzy match)

    Returns match result with vendor_id if found.
    """
    if not any([iban, vat_id, name]):
        err_console.print("[red]Error:[/red] At least one of --iban, --vat-id, or --name required")
        raise typer.Exit(1)

    try:
        with CollmexClient() as client:
            result = client.match_vendor(iban=iban, vat_id=vat_id, name=name)

        if json_output:
            output_json(result)
        else:
            match_type = result.get("match")
            if match_type == "exact":
                console.print(f"[green]Exact match found![/green]")
                console.print(f"Match field: {result.get('match_field')}")
                console.print(f"Vendor ID: {result.get('vendor_id')}")
                vendor = result.get("vendor", {})
                console.print(f"Name: {vendor.get('company_name', '')}")
            elif match_type == "fuzzy":
                console.print("[yellow]Fuzzy matches found:[/yellow]")
                for c in result.get("candidates", []):
                    console.print(f"  [{c['score']}] ID {c['vendor_id']}: {c['name']}")
            else:
                console.print("[red]No match found[/red]")
    except Exception as e:
        handle_error(e)


# =============================================================================
# Open Items Commands
# =============================================================================


@app.command("open-items")
def list_open_items(
    vendor: Annotated[bool, typer.Option("--vendor", "-v", help="Show vendor open items")] = False,
    customer: Annotated[bool, typer.Option("--customer", "-c", help="Show customer open items")] = True,
    vendor_id: Annotated[int | None, typer.Option("--vendor-id", help="Filter by vendor ID")] = None,
    customer_id: Annotated[int | None, typer.Option("--customer-id", help="Filter by customer ID")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """List open items (offene Posten) - unpaid invoices."""
    try:
        with CollmexClient() as client:
            # Default to vendor if --vendor flag is set
            is_vendor = vendor or not customer
            items = client.get_open_items(
                vendor=is_vendor, vendor_id=vendor_id, customer_id=customer_id
            )

        if json_output:
            output_json([i.model_dump() for i in items])
        else:
            item_type = "Vendor" if is_vendor else "Customer"
            rows = [
                [
                    i.vendor_name if is_vendor else i.customer_name,
                    i.invoice_number,
                    i.document_date,
                    i.due_date,
                    i.days_overdue,
                    i.open_amount,
                ]
                for i in items
            ]
            output_table(
                f"Open Items ({item_type})",
                ["Name", "Invoice #", "Date", "Due", "Overdue", "Open Amount"],
                rows,
            )
            total = sum(i.open_amount or Decimal(0) for i in items)
            console.print(f"\n[dim]Total: {len(items)} items, {total} EUR open[/dim]")
    except Exception as e:
        handle_error(e)


# =============================================================================
# Bookings Commands
# =============================================================================


@app.command("bookings")
def list_bookings(
    account: Annotated[int | None, typer.Option("--account", "-a", help="Filter by account number")] = None,
    vendor_id: Annotated[int | None, typer.Option("--vendor-id", help="Filter by vendor ID")] = None,
    customer_id: Annotated[int | None, typer.Option("--customer-id", help="Filter by customer ID")] = None,
    year: Annotated[int | None, typer.Option("--year", "-y", help="Fiscal year")] = None,
    search: Annotated[str | None, typer.Option("--search", "-s", help="Search in booking text")] = None,
    date_from: Annotated[str | None, typer.Option("--from", help="Start date (YYYY-MM-DD)")] = None,
    date_to: Annotated[str | None, typer.Option("--to", help="End date (YYYY-MM-DD)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """List accounting documents/bookings (Buchungen)."""
    try:
        from_date = date.fromisoformat(date_from) if date_from else None
        to_date = date.fromisoformat(date_to) if date_to else None

        with CollmexClient() as client:
            bookings = client.get_bookings(
                fiscal_year=year,
                account_number=account,
                vendor_id=vendor_id,
                customer_id=customer_id,
                text=search,
                date_from=from_date,
                date_to=to_date,
            )

        if json_output:
            output_json([b.model_dump() for b in bookings])
        else:
            rows = [
                [
                    b.booking_id,
                    b.document_date,
                    b.account_number,
                    b.debit_credit,
                    b.amount,
                    b.booking_text[:40] if b.booking_text else "",
                ]
                for b in bookings
            ]
            output_table(
                "Bookings",
                ["ID", "Date", "Account", "D/C", "Amount", "Text"],
                rows,
            )
            console.print(f"\n[dim]Total: {len(bookings)} bookings[/dim]")
    except Exception as e:
        handle_error(e)


@app.command("unmatched")
def list_unmatched(
    account: Annotated[int, typer.Option("--account", "-a", help="Bank account number")] = 1200,
    year: Annotated[int | None, typer.Option("--year", "-y", help="Fiscal year")] = None,
    date_from: Annotated[str | None, typer.Option("--from", help="Start date (YYYY-MM-DD)")] = None,
    date_to: Annotated[str | None, typer.Option("--to", help="End date (YYYY-MM-DD)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """List unmatched bank transactions (missing receipts/invoices).

    Shows bank account entries that don't have a matching vendor or customer invoice.
    These are typically entries that need a receipt to be uploaded.
    """
    try:
        from_date = date.fromisoformat(date_from) if date_from else None
        to_date = date.fromisoformat(date_to) if date_to else None

        with CollmexClient() as client:
            unmatched = client.get_unmatched_bank_transactions(
                bank_account=account,
                fiscal_year=year,
                date_from=from_date,
                date_to=to_date,
            )

        if json_output:
            output_json([b.model_dump() for b in unmatched])
        else:
            rows = [
                [
                    b.booking_id,
                    b.document_date,
                    b.debit_credit,
                    b.amount,
                    b.booking_text[:50] if b.booking_text else "",
                ]
                for b in unmatched
            ]
            output_table(
                f"Unmatched Bank Transactions (Account {account})",
                ["ID", "Date", "D/C", "Amount", "Text"],
                rows,
            )
            console.print(f"\n[dim]Total: {len(unmatched)} unmatched transactions[/dim]")
            console.print("[yellow]These entries need receipts/invoices to be matched.[/yellow]")
    except Exception as e:
        handle_error(e)


# =============================================================================
# Vendor Invoice Commands
# =============================================================================


@app.command("vendor-invoice")
def create_vendor_invoice(
    vendor_id: Annotated[int, typer.Option("--vendor-id", "-v", help="Vendor ID")],
    invoice_number: Annotated[str, typer.Option("--invoice", "-i", help="Invoice number")],
    invoice_date: Annotated[str, typer.Option("--date", "-d", help="Invoice date (YYYY-MM-DD)")],
    net_amount: Annotated[float, typer.Option("--net", "-n", help="Net amount (full VAT rate)")],
    booking_text: Annotated[str | None, typer.Option("--text", "-t", help="Booking text")] = None,
    tax_amount: Annotated[float | None, typer.Option("--tax", help="Tax amount (auto-calculated if empty)")] = None,
    account: Annotated[int | None, typer.Option("--account", "-a", help="Expense account (default: 3200)")] = None,
    cost_center: Annotated[str | None, typer.Option("--cost-center", help="Cost center")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Create a vendor invoice (Lieferantenrechnung).

    Books an expense in accounting with the specified vendor.
    """
    try:
        inv_date = date.fromisoformat(invoice_date)

        invoice = VendorInvoice(
            vendor_id=vendor_id,
            invoice_number=invoice_number,
            invoice_date=inv_date,
            net_amount_full_tax=Decimal(str(net_amount)),
            tax_full=Decimal(str(tax_amount)) if tax_amount else None,
            booking_text=booking_text or "",
            account_full_tax=account,
            cost_center=cost_center or "",
        )

        with CollmexClient() as client:
            result = client.create_vendor_invoice(invoice)

        if json_output:
            output_json({"status": "created", "invoice": invoice.model_dump(), "response": result})
        else:
            console.print(f"[green]Vendor invoice created successfully[/green]")
            console.print(f"Vendor: {vendor_id}")
            console.print(f"Invoice: {invoice_number}")
            console.print(f"Amount: {net_amount} EUR (net)")
    except Exception as e:
        handle_error(e)


# =============================================================================
# ZUGFeRD Commands
# =============================================================================


@app.command("invoice-send")
def send_invoice(
    pdf: Annotated[str, typer.Argument(help="Path to PDF file to send")],
    xml: Annotated[str | None, typer.Option("--xml", "-x", help="Path to ZUGFeRD XML file (optional)")] = None,
    recipient: Annotated[str | None, typer.Option("--to", help="Recipient email (defaults to COLLMEX_ACCOUNTING_EMAIL)")] = None,
    subject: Annotated[str | None, typer.Option("--subject", "-s", help="Email subject")] = None,
    body: Annotated[str | None, typer.Option("--body", "-b", help="Email body text")] = None,
) -> None:
    """Send vendor invoice PDF (with optional ZUGFeRD XML) to accounting.

    The PDF will be sent to the configured accounting email address.
    If a ZUGFeRD XML is provided, it will be attached for automatic import.

    Requires SMTP configuration via environment variables:
    - COLLMEX_SMTP_HOST, COLLMEX_SMTP_USER, COLLMEX_SMTP_PASSWORD, COLLMEX_SMTP_FROM
    - COLLMEX_ACCOUNTING_EMAIL (optional, can override with --to)
    """
    from pathlib import Path

    from .email import send_invoice_email

    try:
        # Read XML content if provided
        xml_content = None
        if xml:
            xml_path = Path(xml)
            if not xml_path.exists():
                err_console.print(f"[red]XML file not found: {xml}[/red]")
                raise typer.Exit(1)
            xml_content = xml_path.read_text(encoding="utf-8")

        send_invoice_email(
            pdf_path=pdf,
            xml_content=xml_content,
            recipient=recipient,
            subject=subject,
            body=body,
        )

        console.print(f"[green]Invoice sent successfully![/green]")
        if recipient:
            console.print(f"Recipient: {recipient}")
        else:
            console.print("Recipient: (from COLLMEX_ACCOUNTING_EMAIL)")
        console.print(f"PDF: {pdf}")
        if xml:
            console.print(f"XML: {xml}")

    except Exception as e:
        handle_error(e)


@app.command("zugferd-create")
def create_zugferd(
    vendor_id: Annotated[int, typer.Option("--vendor-id", "-v", help="Vendor ID from Collmex")],
    invoice_number: Annotated[str, typer.Option("--invoice", "-i", help="Invoice number")],
    invoice_date: Annotated[str, typer.Option("--date", "-d", help="Invoice date (YYYY-MM-DD)")],
    description: Annotated[str, typer.Option("--desc", help="Line item description")],
    net_amount: Annotated[float, typer.Option("--net", "-n", help="Net amount")],
    tax_rate: Annotated[float, typer.Option("--tax-rate", help="Tax rate (e.g., 19.0)")] = 19.0,
    quantity: Annotated[float, typer.Option("--qty", help="Quantity")] = 1.0,
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output file path")] = None,
    buyer_id: Annotated[str | None, typer.Option("--buyer-id", help="Your customer ID at the vendor")] = None,
    due_date: Annotated[str | None, typer.Option("--due", help="Payment due date (YYYY-MM-DD)")] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Additional notes")] = None,
) -> None:
    """Generate a ZUGFeRD XML for a vendor invoice.

    Fetches vendor data from Collmex and generates an EN 16931 compliant XML.
    Buyer data is taken from COLLMEX_BUYER_* environment variables.
    """
    from .zugferd import create_zugferd_xml, save_zugferd_xml

    try:
        inv_date = date.fromisoformat(invoice_date)
        payment_due = date.fromisoformat(due_date) if due_date else None

        # Fetch vendor from Collmex
        with CollmexClient() as client:
            vendors = client.get_vendors(vendor_id=vendor_id)

        if not vendors:
            err_console.print(f"[red]Vendor {vendor_id} not found[/red]")
            raise typer.Exit(1)

        vendor = vendors[0]

        # Create line items
        line_items = [
            {
                "description": description,
                "quantity": Decimal(str(quantity)),
                "unit_price": Decimal(str(net_amount)) / Decimal(str(quantity)),
                "tax_rate": Decimal(str(tax_rate)),
                "unit": "C62",  # pieces
            }
        ]

        # Generate XML
        xml_content = create_zugferd_xml(
            vendor=vendor,
            invoice_number=invoice_number,
            invoice_date=inv_date,
            line_items=line_items,
            buyer_customer_id=buyer_id,
            due_date=payment_due,
            notes=notes,
        )

        # Output
        if output:
            save_zugferd_xml(xml_content, output)
            console.print(f"[green]ZUGFeRD XML saved to {output}[/green]")
        else:
            print(xml_content)

    except Exception as e:
        handle_error(e)


# =============================================================================
# Utility Commands
# =============================================================================


@app.command("test")
def test_connection() -> None:
    """Test the Collmex API connection."""
    try:
        with CollmexClient() as client:
            # Try to fetch vendors as a simple test
            vendors = client.get_vendors()
        console.print("[green]Connection successful![/green]")
        console.print(f"Found {len(vendors)} vendors in your account.")
    except Exception as e:
        handle_error(e)


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Show version and exit")
    ] = False,
) -> None:
    """Collmex CLI - LLM-friendly wrapper for Collmex accounting API."""
    if version:
        console.print(f"collmex-cli {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
