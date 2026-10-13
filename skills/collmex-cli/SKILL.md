---
name: collmex-cli
description: Query Collmex vendors, open items and bookings, or prepare a requested vendor invoice and ZUGFeRD document using the collmex CLI.
---

# Collmex CLI

Use the installed `collmex` CLI. Resolve source and current instructions through
`ccore repo resolve cognovis/collmex-cli`; do not rely on historical checkout
paths. Inspect `collmex --help` and the affected subcommand help for the actual
installed version.

## Configuration and reads

Configuration comes from `COLLMEX_*` environment, the XDG
`~/.config/collmex-cli/config.toml` credentials section, then the current
directory's `.env`. Use configured credentials without printing them; render
missing files from their tracked templates. Relevant groups include API
customer/company/user/password, optional SMTP/accounting recipient and buyer
details. Never put values in source or tool output.

Read-only examples, with concrete filters and bounded projections:

```bash
collmex vendors --search "<supplier>" --json
collmex vendor-match --iban "<iban>" --vat-id "<vat-id>" --name "<supplier>"
collmex open-items --vendor --vendor-id <id> --json
collmex bookings --vendor-id <id> --year <year> --json
collmex unmatched --account <bank-ledger-account> --year <year> --json
collmex bank-statements --account "<configured-name>" --status pending --json
```

`vendor-match` checks exact IBAN, then exact VAT ID, then fuzzy name. Resolve an
ambiguous match using verified invoice details; never invent a vendor ID.
`bookings` and `unmatched` accept `--from`/`--to` ISO dates.
`bank-statements --from` uses DD.MM.YYYY instead. Inspect help rather than
transferring flags between commands. Avoid printing entire ledgers or customer
records; project only needed fields. `collmex test` checks the configured API
connection and can contact the live accounting system.

## Prepare vendor and invoice

Before any write, verify the existing vendor, invoice number, fiscal year,
amounts, tax treatment, expense account and cost center. Search existing bookings
for duplicates; a failed query does not prove absence. Do not post into a closed
fiscal year or infer an accounting treatment from a generic example.

Vendor creation uses `vendor-create --company` with optional `--street`,
`--zip`, `--city`, `--country`, `--email`, `--iban`, `--vat-id`.
Update uses `vendor-update --vendor-id` and `--name`/`--postal-code`
rather than creation's `--company`/`--zip`. Verify the created/updated
record before referring to its ID.

For an authorized posting, call the native command directly:

```bash
collmex vendor-invoice --vendor-id <id> --invoice "<invoice-number>" \
  --date <YYYY-MM-DD> --net <net-amount> --tax <tax-amount> \
  --account <expense-account> --text "<booking-text>" --json
```

`vendor-invoice` books an expense. Its default account is 3200 and omitted tax
is auto-calculated; verify both rather than relying on them. Optional
`--cost-center` uses the intended configured center. Read back the booking and
report its identifier. Retrying a write needs evidence that the first attempt did
not already succeed; do not create a second posting after an ambiguous response.

## ZUGFeRD document and delivery

For a requested vendor document:

```bash
collmex zugferd-create --vendor-id <id> --invoice "<invoice-number>" \
  --date <YYYY-MM-DD> --desc "<line-description>" --net <net-amount> \
  --tax-rate <percentage> --output "<explicit-output.xml>"
```

Optional flags include `--qty`, `--buyer-id`, `--due` and `--notes`.
Preserve existing output files. Validate identity, totals, tax and required buyer/
seller information using the owning document-validation workflow. Do not use
`--force` to skip missing seller validation.

`invoice-send <pdf> --xml <xml> --to <recipient>` sends content by email.
Review attachments and the exact recipient first; a default
`COLLMEX_ACCOUNTING_EMAIL` is configuration, not permission to send.

Accounting/billing changes fall under the active production approval boundary.
Customer or partner messages require explicit authorization for the content and
recipient. Prepare and verify the concrete result before asking when approval is
needed. Pure reads and local preparation do not introduce an approval gate.
The skill grants no permission to post, pay or send merely because it was loaded.

The former vendor and ZUGFeRD example scripts are dissolved into these native
command instructions; no skill-local executable wrapper is required.
