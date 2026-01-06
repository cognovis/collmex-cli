# collmex-cli

LLM-friendly CLI wrapper for the [Collmex](https://www.collmex.de) accounting API (Buchhaltung Pro).

## Installation

```bash
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

### Vendor Invoices (Lieferantenrechnungen)

```bash
# Create a vendor invoice
collmex vendor-invoice \
  --vendor-id 123 \
  --invoice "INV-2024-001" \
  --date 2024-01-15 \
  --net 100.00 \
  --text "Office supplies"
```

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
- `OPEN_ITEMS_GET` / `OPEN_ITEM` - Query open items
- `ACCDOC_GET` / `ACCDOC` - Query accounting documents/bookings

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest
```
