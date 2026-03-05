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
from .app_config import load_config
from .client import CollmexClient
from .models import InvoicePayment, Vendor, VendorInvoice


def check_for_update() -> None:
    """Check PyPI for a newer version and print a hint if available."""
    import re

    import httpx

    def _normalize(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in re.sub(r"[^0-9.]", "", v).split(".") if x)

    try:
        resp = httpx.get("https://pypi.org/pypi/collmex-cli/json", timeout=3)
        if resp.status_code != 200:
            return
        latest = resp.json()["info"]["version"]
        if _normalize(latest) > _normalize(__version__):
            Console(stderr=True).print(
                f"[dim]Update available: {__version__} → {latest}  "
                f"(uv tool upgrade collmex-cli)[/dim]"
            )
    except Exception:
        pass

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


# =============================================================================
# Invoice Payments Commands
# =============================================================================


@app.command("invoice-payments")
def list_invoice_payments(
    invoice_number: Annotated[str | None, typer.Option("--invoice-number", "-i", help="Filter by invoice number")] = None,
    customer_id: Annotated[int | None, typer.Option("--customer-id", "-c", help="Filter by customer ID")] = None,
    date_from: Annotated[str | None, typer.Option("--date-from", help="Payment date from (YYYY-MM-DD)")] = None,
    date_to: Annotated[str | None, typer.Option("--date-to", help="Payment date to (YYYY-MM-DD)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """List invoice payments (Rechnungszahlungen)."""
    try:
        from_date = date.fromisoformat(date_from) if date_from else None
        to_date = date.fromisoformat(date_to) if date_to else None

        with CollmexClient() as client:
            payments = client.get_invoice_payments(
                invoice_number=invoice_number,
                customer_id=customer_id,
                date_from=from_date,
                date_to=to_date,
            )

        if json_output:
            output_json([p.model_dump() for p in payments])
        else:
            rows = [
                [
                    p.invoice_number,
                    p.customer_id,
                    p.customer_name,
                    p.payment_date,
                    p.payment_amount,
                    p.payment_method,
                    p.booking_id,
                ]
                for p in payments
            ]
            output_table(
                "Invoice Payments",
                ["Invoice #", "Customer ID", "Customer", "Date", "Amount", "Method", "Booking ID"],
                rows,
            )
            console.print(f"\n[dim]Total: {len(payments)} payments[/dim]")
    except Exception as e:
        handle_error(e)


@app.command("bank-status")
def bank_status(
    account: Annotated[int | None, typer.Option("--account", "-a", help="Single bank account number (default: all from config)")] = None,
    year: Annotated[int | None, typer.Option("--year", "-y", help="Fiscal year")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Show the date of the last bank statement import.

    Without --account, queries all bank accounts defined in
    ~/.config/collmex-cli/config.toml.

    Useful to know the start date for exporting new statements from MoneyMoney.
    """
    from .app_config import config_path

    try:
        cfg = load_config()

        # Single account or all configured accounts
        if account is not None:
            accounts = {"Account": account}
        elif cfg.bank_accounts:
            accounts = cfg.bank_accounts
        else:
            err_console.print(f"[red]No bank accounts configured.[/red]")
            err_console.print(f"Either use [bold]--account 1200[/bold] or configure accounts in:")
            err_console.print(f"  [dim]{config_path()}[/dim]")
            err_console.print()
            err_console.print("[dim]Example config.toml:[/dim]")
            err_console.print('[dim][bank_accounts][/dim]')
            err_console.print('[dim]"Geschaeftskonto" = 1200[/dim]')
            raise typer.Exit(1)

        results = []
        with CollmexClient() as client:
            for name, acct_nr in accounts.items():
                result = client.get_last_bank_booking_date(
                    bank_account=acct_nr,
                    fiscal_year=year,
                )
                result["name"] = name
                results.append(result)

        if json_output:
            output_json(results if len(results) > 1 else results[0])
        else:
            table = Table(title=f"Bank Status (fiscal year {results[0]['fiscal_year']})")
            table.add_column("Account")
            table.add_column("Number", justify="right")
            table.add_column("Last Booking", justify="center")
            table.add_column("Bookings", justify="right")
            for r in results:
                last = str(r["last_date"]) if r["last_date"] else "[yellow]none[/yellow]"
                table.add_row(r["name"], str(r["account"]), last, str(r["booking_count"]))
            console.print(table)

            # Show the overall earliest "last_date" as suggested MoneyMoney export start
            dates = [r["last_date"] for r in results if r["last_date"]]
            if dates:
                earliest = min(dates)
                console.print(f"\n[dim]Export from MoneyMoney starting: {earliest}[/dim]")
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
            print(xml_content.decode("utf-8") if isinstance(xml_content, bytes) else xml_content)

    except Exception as e:
        handle_error(e)


# =============================================================================
# Web Automation Commands
# =============================================================================


@app.command("upload-statement")
def upload_statement(
    file: Annotated[str, typer.Argument(help="Path to MT940/CAMT bank statement file")],
    account: Annotated[str | None, typer.Option("--account", "-a", help="Bank account name from config")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Upload a bank statement (MT940/CAMT) via Collmex web UI.

    Requires playwright-cli and a saved auth state. Create one with:
        playwright-cli -s=collmex open https://www.collmex.de
        # Log in manually
        playwright-cli -s=collmex state-save ~/.local/share/collmex-cli/auth-state.json
        playwright-cli -s=collmex close
    """
    from pathlib import Path

    from .web import CollmexWeb, CollmexWebError, PlaywrightCliError

    file_path = Path(file)
    if not file_path.exists():
        err_console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    cfg = load_config()
    account_name = account or next(iter(cfg.bank_accounts), None)
    if not account_name:
        err_console.print("[red]No account specified and none configured.[/red]")
        err_console.print("Use --account NAME or configure [bank_accounts] in config.toml")
        raise typer.Exit(1)

    try:
        web = CollmexWeb(app_config=cfg)
        try:
            result = web.upload_statement(file_path, account_name)
        finally:
            web.close()

        if json_output:
            output_json(result)
        else:
            console.print(f"[green]{result['message']}[/green]")
            console.print(f"File: {result['file']}")
            console.print(f"Account: {result['account']}")
    except (PlaywrightCliError, CollmexWebError) as e:
        handle_error(e)
    except Exception as e:
        handle_error(e)


@app.command("import-statements")
def import_statements(
    account: Annotated[str | None, typer.Option("--account", "-a", help="Single account name from config (default: all)")] = None,
    date_from: Annotated[str | None, typer.Option("--from", help="Export start date (YYYY-MM-DD, default: last booking date)")] = None,
    all_accounts: Annotated[bool, typer.Option("--all", help="Process all configured MoneyMoney accounts")] = False,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Import bank statements from MoneyMoney into Collmex.

    Full roundtrip:
    1. Get last import date from Collmex (bank-status)
    2. Export from MoneyMoney via `mm export` (sta format)
    3. Upload each .sta file to Collmex web UI

    Requires MoneyMoney to be running and unlocked.
    Requires playwright-cli with a saved Collmex session.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from .web import CollmexWeb, CollmexWebError, PlaywrightCliError

    try:
        cfg = load_config()

        if not cfg.mm_accounts:
            err_console.print("[red]No MoneyMoney accounts configured.[/red]")
            err_console.print("Add [mm_accounts] section to config.toml:")
            err_console.print('[dim]"Fyrst Base" = "Fyrst (1200)"[/dim]')
            raise typer.Exit(1)

        # Determine which accounts to process
        if account:
            # Find MM account(s) mapping to this config account
            mm_pairs = [(mm, cfg_name) for mm, cfg_name in cfg.mm_accounts.items() if cfg_name == account]
            if not mm_pairs:
                # Maybe user passed the MM name directly
                if account in cfg.mm_accounts:
                    mm_pairs = [(account, cfg.mm_accounts[account])]
                else:
                    err_console.print(f"[red]Account '{account}' not found in mm_accounts config.[/red]")
                    raise typer.Exit(1)
        else:
            mm_pairs = list(cfg.mm_accounts.items())

        # Get last booking dates for start date determination
        last_dates: dict[str, date | None] = {}
        if not date_from:
            with CollmexClient() as client:
                for _mm_name, cfg_name in mm_pairs:
                    acct_nr = cfg.bank_accounts.get(cfg_name)
                    if acct_nr:
                        result = client.get_last_bank_booking_date(bank_account=acct_nr)
                        last_dates[cfg_name] = result.get("last_date")

        results = []
        web = CollmexWeb(app_config=cfg)
        try:
            for mm_name, cfg_name in mm_pairs:
                console.print(f"\n[bold]{cfg_name}[/bold] (MoneyMoney: {mm_name})")

                # Determine export start date
                if date_from:
                    start = date_from
                elif last_dates.get(cfg_name):
                    start = str(last_dates[cfg_name])
                else:
                    err_console.print(f"  [yellow]No last booking date found, skipping.[/yellow]")
                    err_console.print("  Use --from DATE to specify a start date.")
                    continue

                console.print(f"  Exporting from {start}...")

                # Export from MoneyMoney via mm CLI
                with tempfile.NamedTemporaryFile(suffix=".sta", delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                try:
                    mm_result = subprocess.run(
                        ["mm", "export", "-a", mm_name, "--from", start, "-f", "sta", "-o", str(tmp_path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if mm_result.returncode != 0:
                        err_console.print(f"  [red]mm export failed:[/red] {mm_result.stderr.strip()}")
                        continue

                    # Check if file has content
                    if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                        console.print("  [dim]No new transactions to export.[/dim]")
                        continue

                    console.print(f"  Uploading {tmp_path.name} ({tmp_path.stat().st_size} bytes)...")

                    # Upload to Collmex
                    upload_result = web.upload_statement(tmp_path, cfg_name)
                    console.print(f"  [green]{upload_result['message']}[/green]")
                    results.append(upload_result)

                finally:
                    tmp_path.unlink(missing_ok=True)

        finally:
            web.close()

        if json_output:
            output_json(results)
        elif not results:
            console.print("\n[dim]No statements were imported.[/dim]")
        else:
            console.print(f"\n[green]Done: {len(results)} account(s) imported.[/green]")

    except (PlaywrightCliError, CollmexWebError) as e:
        handle_error(e)
    except Exception as e:
        handle_error(e)


@app.command("import-statements")
def import_statements(
    account: Annotated[str | None, typer.Option("--account", "-a", help="Single account name from config (default: all)")] = None,
    date_from: Annotated[str | None, typer.Option("--from", help="Export start date (YYYY-MM-DD, default: last booking date)")] = None,
    all_accounts: Annotated[bool, typer.Option("--all", help="Process all configured MoneyMoney accounts")] = False,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Import bank statements from MoneyMoney into Collmex.

    Full roundtrip:
    1. Get last import date from Collmex (bank-status)
    2. Export from MoneyMoney via `mm export` (sta format)
    3. Upload each .sta file to Collmex web UI

    Requires MoneyMoney to be running and unlocked.
    Requires playwright-cli with a saved Collmex session.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from .web import CollmexWeb, CollmexWebError, PlaywrightCliError

    try:
        cfg = load_config()

        if not cfg.mm_accounts:
            err_console.print("[red]No MoneyMoney accounts configured.[/red]")
            err_console.print("Add [mm_accounts] section to config.toml:")
            err_console.print('[dim]"Fyrst Base" = "Fyrst (1200)"[/dim]')
            raise typer.Exit(1)

        # Determine which accounts to process
        if account:
            # Find MM account(s) mapping to this config account
            mm_pairs = [
                (mm, cfg_name)
                for mm, cfg_name in cfg.mm_accounts.items()
                if cfg_name == account
            ]
            if not mm_pairs:
                # Maybe user passed the MM name directly
                if account in cfg.mm_accounts:
                    mm_pairs = [(account, cfg.mm_accounts[account])]
                else:
                    err_console.print(
                        f"[red]Account '{account}' not found in mm_accounts config.[/red]"
                    )
                    raise typer.Exit(1)
        else:
            mm_pairs = list(cfg.mm_accounts.items())

        # Get last booking dates for start date determination
        last_dates: dict[str, date | None] = {}
        if not date_from:
            with CollmexClient() as client:
                for _mm_name, cfg_name in mm_pairs:
                    acct_nr = cfg.bank_accounts.get(cfg_name)
                    if acct_nr:
                        result = client.get_last_bank_booking_date(bank_account=acct_nr)
                        last_dates[cfg_name] = result.get("last_date")

        results = []
        web = CollmexWeb(app_config=cfg)
        try:
            for mm_name, cfg_name in mm_pairs:
                console.print(f"\n[bold]{cfg_name}[/bold] (MoneyMoney: {mm_name})")

                # Determine export start date
                if date_from:
                    start = date_from
                elif last_dates.get(cfg_name):
                    start = str(last_dates[cfg_name])
                else:
                    err_console.print(
                        "  [yellow]No last booking date found, skipping.[/yellow]"
                    )
                    err_console.print("  Use --from DATE to specify a start date.")
                    continue

                console.print(f"  Exporting from {start}...")

                # Export from MoneyMoney via mm CLI
                with tempfile.NamedTemporaryFile(suffix=".sta", delete=False) as tmp:
                    tmp_path = Path(tmp.name)

                try:
                    mm_result = subprocess.run(
                        [
                            "mm",
                            "export",
                            "-a",
                            mm_name,
                            "--from",
                            start,
                            "-f",
                            "sta",
                            "-o",
                            str(tmp_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if mm_result.returncode != 0:
                        err_console.print(
                            f"  [red]mm export failed:[/red] {mm_result.stderr.strip()}"
                        )
                        continue

                    # Check if file has content
                    if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                        console.print("  [dim]No new transactions to export.[/dim]")
                        continue

                    console.print(
                        f"  Uploading {tmp_path.name} ({tmp_path.stat().st_size} bytes)..."
                    )

                    # Upload to Collmex
                    upload_result = web.upload_statement(tmp_path, cfg_name)
                    console.print(f"  [green]{upload_result['message']}[/green]")
                    results.append(upload_result)

                finally:
                    tmp_path.unlink(missing_ok=True)

        finally:
            web.close()

        if json_output:
            output_json(results)
        elif not results:
            console.print("\n[dim]No statements were imported.[/dim]")
        else:
            console.print(f"\n[green]Done: {len(results)} account(s) imported.[/green]")

    except (PlaywrightCliError, CollmexWebError) as e:
        handle_error(e)
    except Exception as e:
        handle_error(e)


@app.command("pending-bookings")
def pending_bookings(
    account: Annotated[str | None, typer.Option("--account", "-a", help="Bank account name from config")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
) -> None:
    """Show pending bookings ("Zu buchen") from Collmex web UI.

    Lists imported but not yet booked bank transactions.

    Requires playwright-cli and a saved auth state.
    """
    from .web import CollmexWeb, CollmexWebError, PlaywrightCliError

    cfg = load_config()
    account_name = account or next(iter(cfg.bank_accounts), None)
    if not account_name:
        err_console.print("[red]No account specified and none configured.[/red]")
        err_console.print("Use --account NAME or configure [bank_accounts] in config.toml")
        raise typer.Exit(1)

    try:
        web = CollmexWeb(app_config=cfg)
        try:
            bookings = web.get_pending_bookings(account_name)
        finally:
            web.close()

        if json_output:
            output_json(bookings)
        else:
            if not bookings:
                console.print("[dim]No pending bookings found.[/dim]")
                return

            # Use keys from first row as columns
            columns = list(bookings[0].keys())
            rows = [[b.get(c, "") for c in columns] for b in bookings]
            output_table(f"Pending Bookings ({account_name})", columns, rows)
            console.print(f"\n[dim]Total: {len(bookings)} pending bookings[/dim]")
    except (PlaywrightCliError, CollmexWebError) as e:
        handle_error(e)
    except Exception as e:
        handle_error(e)


@app.command("bank-statements")
def bank_statements(
    account: Annotated[str | None, typer.Option("--account", "-a", help="Bank account name from config")] = None,
    date_from: Annotated[str | None, typer.Option("--from", help="Start date DD.MM.YYYY")] = None,
    status: Annotated[str | None, typer.Option("--status", "-s", help="Filter: pending, deferred, excluded, booked, or all")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
    all_accounts: Annotated[bool, typer.Option("--all", help="Query all configured bank accounts")] = False,
) -> None:
    """Show bank statements from Collmex with structured status info.

    Returns each transaction with a normalized status:
      pending  — "Zu buchen" (imported, awaiting booking)
      deferred — "Später buchen" (postponed, e.g. missing invoice)
      excluded — "Nicht buchen" (intentionally skipped)
      booked   — has a Buchung Nr (booking document number)

    Designed for LLM consumption with --json.

    Requires playwright-cli and a saved auth state.
    """
    from .web import CollmexWeb, CollmexWebError, PlaywrightCliError

    # Map CLI status names to Collmex German filter values
    STATUS_TO_COLLMEX = {
        "pending": "Zu buchen",
        "deferred": "Später buchen",
        "excluded": "Nicht buchen",
        "booked": "Gebucht",
        "all": None,
    }

    collmex_status = None
    if status:
        if status not in STATUS_TO_COLLMEX:
            err_console.print(f"[red]Unknown status '{status}'. Use: pending, deferred, excluded, booked, all[/red]")
            raise typer.Exit(1)
        collmex_status = STATUS_TO_COLLMEX[status]

    cfg = load_config()

    if all_accounts:
        accounts = list(cfg.bank_accounts.keys())
    elif account:
        accounts = [account]
    else:
        first = next(iter(cfg.bank_accounts), None)
        if not first:
            err_console.print("[red]No account specified and none configured.[/red]")
            raise typer.Exit(1)
        accounts = [first]

    try:
        web = CollmexWeb(app_config=cfg)
        try:
            all_statements: list[dict] = []
            for acct in accounts:
                stmts = web.get_statements(acct, date_from=date_from, status=collmex_status)
                all_statements.extend(stmts)
        finally:
            web.close()

        if json_output:
            output_json(all_statements)
        else:
            if not all_statements:
                console.print("[dim]No statements found.[/dim]")
                return

            columns = ["date", "amount", "status", "booking_nr", "name", "purpose"]
            rows = [[s.get(c, "") for c in columns] for s in all_statements]
            # Show account in title if single, add column if multiple
            if len(accounts) > 1:
                columns.insert(0, "account")
                rows = [[s.get("account", "")] + r for s, r in zip(all_statements, rows)]
            title = f"Bank Statements ({accounts[0]})" if len(accounts) == 1 else "Bank Statements (all accounts)"
            output_table(title, columns, rows)

            # Summary by status
            from collections import Counter
            counts = Counter(s["status"] for s in all_statements)
            parts = [f"{v} {k}" for k, v in sorted(counts.items())]
            console.print(f"\n[dim]Total: {len(all_statements)} — {', '.join(parts)}[/dim]")

    except (PlaywrightCliError, CollmexWebError) as e:
        handle_error(e)
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


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Show version and exit")
    ] = False,
) -> None:
    """Collmex CLI - LLM-friendly wrapper for Collmex accounting API."""
    if version:
        console.print(f"collmex-cli {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()
    check_for_update()


if __name__ == "__main__":
    app()
