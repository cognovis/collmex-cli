---
name: customer-invoice
description: >-
  Create outgoing customer invoices with collmex-cli. Use when preparing
  customer invoices, Ausgangsrechnungen, or Cognovis billing with Timing,
  travel costs, ZUGFeRD, Collmex booking, and Mail drafts.
requires_standards: [english-only]
---

# Customer Invoice

## Overview

Create a complete outgoing customer invoice from offer context, Timing.app
entries, travel costs, Collmex ZUGFeRD/PDF generation, Collmex booking, and
visible Apple Mail drafts. The workflow must keep the user in control of every
commercial decision and must never send mail automatically.

## When to Use

Use this skill for:

- Creating Cognovis customer invoices from Timing.app entries.
- Creating Ausgangsrechnungen with Collmex and ZUGFeRD output.
- Preparing invoice drafts for a customer and the cognovis bookkeeping inbox (`buchhaltung@cognovis.de`).

Do not use this skill for Google vendor invoices. Use `google-invoice` for that
workflow and do not modify its files.

## Workflow

### 1. Gather Invoice Intent

Ask interactively for:

- Customer name as used under `/Users/malte/Documents/cognovis/Kunden/<Kunde>/`.
- Billing period start and end dates in `YYYY-MM-DD`.
- Short invoice description or project reference.
- Customer email address for the invoice draft.

Look up the Collmex customer ID by running:

```bash
cd ~/code/cli-tools/collmex-cli && uv run collmex customers --json
```

Do not guess customer IDs. Stop and ask the user if the matching customer is
ambiguous.

### 2. Load Offer Context

Read `/Users/malte/Documents/cognovis/Kunden/angebote.json`. Treat the current
file shape as a single JSON object with keys like `kunde`, `adresse`, and
`angebote`.

Find offers for the requested customer and show the relevant offer numbers,
titles, net amounts, and any available `stundensatz` fields as context. Resolve
the hourly rate in this order:

1. `stundensatz` in `angebote.json`.
2. Existing per-customer configuration if present in the repo or customer folder.
3. Interactive prompt.

Do not invent an hourly rate.

### 3. Collect Billable Positions

Query Timing.app entries with:

```python
from datetime import date
from timing_helper import query_timing_entries

timing_result = query_timing_entries(
    customer="<Kunde>",
    start_date=date.fromisoformat("<YYYY-MM-DD>"),
    end_date=date.fromisoformat("<YYYY-MM-DD>"),
    hourly_rate=<resolved_hourly_rate>,
)
```

Collect travel costs with the external customer-invoice helper. The
`scripts/travel_costs.py` module lives in the sussdorff-core library
outside this repo, so prepend its base directory to `sys.path` before
importing:

```python
import sys
sys.path.insert(0, "/Users/malte/code/library/sussdorff-core/skills/business/customer-invoice")
from scripts.travel_costs import get_travel_cost_positions

travel_positions = get_travel_cost_positions(
    "Reisekosten/<kunde>",
    from_date="<YYYY-MM-DD>",
    to_date="<YYYY-MM-DD>",
)
```

If the MoneyMoney category is missing, report the error and ask whether to
continue with manual positions. Never silently drop travel costs.

### 4. Confirm Positions

Build a human-readable summary before generating anything:

- Timing positions: description, hours, hourly rate, net amount.
- Travel cost positions: description, source, date when available, net amount.
- Unassigned Timing entries, if any.
- Net subtotal, VAT assumption, and gross total.

Ask the user to confirm or edit positions. Continue only after explicit
confirmation.

### 5. Determine Invoice Number and Output Paths

Generate the next invoice number with:

```python
from pathlib import Path
from datetime import date
from invoice_number import next_invoice_number

invoice_number = next_invoice_number(
    year=date.today().year,
    month=date.today().month,
    kunden_root=Path("/Users/malte/Documents/cognovis/Kunden"),
)
```

The scheme is `I<YYYY>_<MM>_<NNNN>`, for example `I2026_05_0001`.

Create output under:

```text
/Users/malte/Documents/cognovis/Kunden/<Kunde>/Rechnungen/
```

Use:

- PDF path: `<invoice_number>.pdf`
- XML path: `<invoice_number>.xml`

### 6. Create ZUGFeRD PDF/A-3 and XML

Build the Collmex item JSON from confirmed positions. Use time positions as
quantity/rate lines and travel costs as amount lines accepted by the local
`collmex customer-zugferd-create` command. Inspect command help if the exact
item schema is unclear.

Run Collmex from the cli-tools repo only:

```bash
cd ~/code/cli-tools/collmex-cli && uv run collmex customer-zugferd-create \
  --customer-id <collmex_customer_id> \
  --invoice "<invoice_number>" \
  --date "<invoice_date>" \
  --items '<items_json>' \
  --output "/Users/malte/Documents/cognovis/Kunden/<Kunde>/Rechnungen/<invoice_number>.pdf" \
  --delivery-date "<period_end>" \
  --project-ref "<project_ref>"
```

Verify that both the PDF/A-3 PDF and sidecar XML exist in the Rechnungen
folder before booking the invoice.

### 7. Book Customer Invoice in Collmex

Compute the confirmed net total and run:

```bash
cd ~/code/cli-tools/collmex-cli && uv run collmex customer-invoice \
  --customer-id <collmex_customer_id> \
  --invoice "<invoice_number>" \
  --date "<invoice_date>" \
  --net <net_total> \
  --text "<invoice_description>" \
  --json
```

Check the JSON response for success before creating Mail drafts.

### 8. Create Visible Mail Drafts

Create two visible drafts and send nothing automatically:

```bash
CUSTOMER_EMAIL="<customer@example.com>" \
INVOICE_NUMBER="<invoice_number>" \
PDF_PATH="/Users/malte/Documents/cognovis/Kunden/<Kunde>/Rechnungen/<invoice_number>.pdf" \
XML_PATH="/Users/malte/Documents/cognovis/Kunden/<Kunde>/Rechnungen/<invoice_number>.xml" \
bash library/sussdorff-core/skills/business/customer-invoice/scripts/create_mail_drafts.sh
```

The script creates:

- Customer draft to the interactively provided customer email with the PDF.
- Bookkeeping draft to `buchhaltung@cognovis.de` with PDF and XML. `buchhaltung@cognovis.de` is the role address of the cognovis bookkeeper (currently Herr Koch) AND Collmex's Beleg-Posteingang (IMAP pickup) — one mail reaches both. The PDF lands in Collmex's Belegarchiv and is manually assigned to the CMXUMS booking via "Beleg → Zuordnung" in the Collmex UI. See bead collmex-cli-c12.5 for the planned Buchungsnummer-in-subject enhancement that makes the assignment direct.

### 9. Report Summary

Report:

- Customer, Collmex customer ID, period, invoice number, and net total.
- Created PDF and XML paths.
- Collmex booking result.
- Mail drafts created.
- Any skipped or manually adjusted positions.

## Resources

- `timing_helper.py`: Timing.app query helper.
- `invoice_number.py`: next invoice number scanner.
- `scripts/create_mail_drafts.sh`: visible Apple Mail drafts.
- External travel helper:
  `/Users/malte/code/library/sussdorff-core/skills/business/customer-invoice/scripts/travel_costs.py`.
  This file lives outside the collmex-cli repo and is not shipped with
  this skill, so the import in Step 3 requires
  `sys.path.insert(0, "/Users/malte/code/library/sussdorff-core/skills/business/customer-invoice")`
  before `from scripts.travel_costs import ...`.

## Limitations

- Never send email automatically.
- Never guess customer IDs, email addresses, hourly rates, or invoice positions.
- Never modify `google-invoice`; that workflow is separate.
- Always run Collmex commands as
  `cd ~/code/cli-tools/collmex-cli && uv run collmex ...`.
