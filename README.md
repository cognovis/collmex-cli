# collmex-cli

LLM-friendly CLI wrapper for the [Collmex](https://www.collmex.de) accounting API (Buchhaltung Pro).

## Installation

```bash
# From PyPI (recommended)
uv tool install collmex-cli

# From source (development)
uv pip install -e .
```

## Configuration

Set environment variables (or use a `.env` file):

```bash
export COLLMEX_CUSTOMER_ID="your_customer_id"
export COLLMEX_COMPANY_ID="1"  # usually 1
export COLLMEX_USERNAME="your_username"
export COLLMEX_PASSWORD="your_password"
```

### Seller master data (required for PDF invoice rendering)

```bash
export COLLMEX_SELLER_NAME="cognovis GmbH"
export COLLMEX_SELLER_STREET="Musterstraße 1"
export COLLMEX_SELLER_ZIP="12345"
export COLLMEX_SELLER_CITY="Berlin"
export COLLMEX_SELLER_VAT_ID="DE123456789"
export COLLMEX_SELLER_HRB="HRB 12345"
export COLLMEX_SELLER_IBAN="DE00 1234 5678 9012 3456 78"
export COLLMEX_SELLER_BIC="BELADEBEXXX"

# Optional
export COLLMEX_SELLER_AMTSGERICHT="Amtsgericht Berlin-Charlottenburg"
export COLLMEX_SELLER_GESCHAEFTSFUEHRUNG="Max Mustermann"
export COLLMEX_SELLER_PHONE="+49 30 123456"
export COLLMEX_SELLER_FAX="+49 30 123457"
export COLLMEX_SELLER_WEB="https://www.cognovis.de"
export COLLMEX_SELLER_EMAIL="info@cognovis.de"
export COLLMEX_SELLER_BANK_NAME="Deutsche Bank"
```

## Usage

### Test Connection

```bash
collmex test
```

### Vendors (Lieferanten)

```bash
# List all vendors
collmex vendors

# Search vendors
collmex vendors --search "Amazon"

# Output as JSON (LLM-friendly)
collmex vendors --json

# Create a vendor
collmex vendor-create --company "New Supplier GmbH" --city "Berlin" --email "info@supplier.de"
```

### Open Items (Offene Posten)

```bash
# List vendor open items (unpaid vendor invoices)
collmex open-items --vendor

# List customer open items
collmex open-items --customer

# Output as JSON
collmex open-items --vendor --json
```

### Bookings (Buchungen)

```bash
# List all bookings
collmex bookings

# Filter by account
collmex bookings --account 1200

# Filter by date range
collmex bookings --from 2024-01-01 --to 2024-12-31

# Search in booking text
collmex bookings --search "Amazon"
```

### Unmatched Bank Transactions

```bash
# Find bank transactions without matching invoices/receipts
collmex unmatched

# For a specific bank account
collmex unmatched --account 1200

# Output as JSON
collmex unmatched --json
```

### Customer Invoices (Ausgangsrechnungen)

```bash
# Book a customer invoice in accounting (no invoicing module required)
collmex customer-invoice \
  --customer-id 10001 \
  --invoice "RE-2024-042" \
  --date 2024-01-15 \
  --net 1000.00 \
  --tax-rate 19 \
  --text "Consulting January 2024" \
  --account 8400

# Override the computed tax amount explicitly
collmex customer-invoice --customer-id 10001 --invoice "RE-2024-043" \
  --date 2024-01-15 --net 500.00 --tax 95.00

# Output as JSON — includes buchungsnummer from Collmex NEW_OBJECT_ID response
collmex customer-invoice --customer-id 10001 --invoice "RE-2024-044" \
  --date 2024-01-15 --net 200.00 --json
# → {"status": "created", "invoice": {...}, "buchungsnummer": 42}
```

After booking, the invoice appears in `open-items --customer` until payment is received and in `bookings` with the debtor and revenue accounts.

### ZUGFeRD Customer Invoice (PDF/A-3 with embedded XML)

Generate a ZUGFeRD-compliant PDF/A-3 invoice with embedded EN16931 XML. Seller is always
cognovis (VAT ID DE118620281); buyer master data is fetched from Collmex by customer ID.

```bash
collmex customer-zugferd-create \
  --customer-id 10001 \
  --invoice "RE-2026-042" \
  --date 2026-05-21 \
  --items '[
    {"description": "Consulting May 2026", "quantity": 8, "unit_price": 150.00, "vat_rate": 19},
    {"description": "Travel expenses", "quantity": 1, "unit_price": 42.50, "vat_rate": 19}
  ]' \
  --output rechnung-RE-2026-042.pdf

# With optional metadata
collmex customer-zugferd-create \
  --customer-id 10001 \
  --invoice "RE-2026-042" \
  --date 2026-05-21 \
  --items '[{"description": "Consulting", "quantity": 8, "unit_price": 150.00, "vat_rate": 19}]' \
  --output rechnung.pdf \
  --delivery-date 2026-05-31 \
  --due 2026-06-14 \
  --payment-terms "Zahlbar innerhalb von 14 Tagen" \
  --project-ref "Projekt XYZ" \
  --notes "Gemäß Rahmenvertrag vom 01.01.2026"
```

The output file is a PDF/A-3 with the ZUGFeRD XML (`factur-x.xml`) attached as
`AFRelationship=Alternative`. It passes EN16931 schematron validation automatically;
missing seller or buyer master-data fields produce a clear error listing the affected
fields before any file is written.

Seller master data must be present in `CollmexConfig` (env vars starting with
`COLLMEX_SELLER_`). See the *Seller master data* section under Configuration above.

### Vendor Invoices (Lieferantenrechnungen)

```bash
# Create a vendor invoice
collmex vendor-invoice \
  --vendor-id 123 \
  --invoice "INV-2024-001" \
  --date 2024-01-15 \
  --net 100.00 \
  --text "Office supplies"

# Output as JSON — includes buchungsnummer from Collmex NEW_OBJECT_ID response
collmex vendor-invoice --vendor-id 123 --invoice "INV-2024-001" \
  --date 2024-01-15 --net 100.00 --json
# → {"status": "created", "invoice": {...}, "buchungsnummer": 43}
```

### Invoice PDF Rendering

Generate a cognovis-layout PDF from structured invoice data:

```python
from collmex_cli.invoice_renderer import render_invoice, InvoiceData, InvoiceLineItem

data = InvoiceData(
    company_name="Acme GmbH",
    company_contact_name="Jane Doe",
    address_line1="Hauptstraße 5",
    postal_code="10115",
    city="Berlin",
    country="DE",
    vat_number="DE987654321",
    invoice_nr="2026-0042",
    invoice_date="21.05.2026",
    delivery_date="21.05.2026",
    project_ref="Projekt XYZ",
    line_items=[
        InvoiceLineItem(name="Beratung", quantity="8 h", unit_price="150,00 €", amount="1.200,00 €"),
    ],
    subtotal="1.200,00 €",
    vat_rate="19%",
    vat_amount="228,00 €",
    total="1.428,00 €",
)

pdf_bytes = render_invoice(data)
with open("rechnung.pdf", "wb") as f:
    f.write(pdf_bytes)
```

Seller master data is read from `CollmexConfig`. Missing mandatory fields raise a `ValueError`
listing the affected field names.

## LLM Integration

All commands support `--json` output for easy parsing by LLMs:

```bash
collmex vendors --json | jq '.[] | select(.city == "Berlin")'
```

## Workflow: Matching Bank Transactions

1. Import bank statement (MT940) via Collmex Web UI
2. Find unmatched transactions:
   ```bash
   collmex unmatched --json
   ```
3. For each unmatched transaction, create vendor invoice:
   ```bash
   collmex vendor-invoice --vendor-id 123 --invoice "INV-001" --date 2024-01-15 --net 50.00
   ```

## API Coverage

Currently supported Collmex record types:

- `VENDOR_GET` / `CMXLIF` - Query and create vendors
- `CMXLRN` - Create vendor invoices
- `CMXUMS` - Create customer invoices (outgoing invoices in accounting)
- `OPEN_ITEMS_GET` / `OPEN_ITEM` - Query open items
- `ACCDOC_GET` / `ACCDOC` - Query accounting documents/bookings

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest
```
