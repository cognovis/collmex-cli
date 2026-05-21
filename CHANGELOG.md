## [Unreleased]

### Added

- **`customer-invoice` skill**: Interactive agent workflow for creating outgoing cognovis invoices end-to-end.
  - Collects billable positions from Timing.app (`query_timing_entries`) and travel costs from MoneyMoney or manual mileage entry.
  - Calls `collmex customer-zugferd-create` to generate a ZUGFeRD PDF/A-3 and sidecar XML, then books the invoice via `collmex customer-invoice`.
  - Creates two visible Apple Mail drafts (customer copy and Steuerberater Koch) — no automatic sending.
  - Invoice number scheme `I<YYYY>_<MM>_<NNNN>` (e.g. `I2026_05_0001`); `invoice_number.py` scans the Kunden directory to determine the next sequential number.
  - `google-invoice` skill is unchanged; the new skill explicitly guards against accidental modification.

- **`customer-zugferd-create` command**: Generate a cognovis customer invoice as a ZUGFeRD-compliant PDF/A-3 file embedding EN16931 XML.
  - Seller is always cognovis (VAT ID DE118620281); buyer master data is fetched from Collmex by `--customer-id`.
  - Accepts `--invoice`, `--date`, `--items` (JSON line-item array with `description`, `quantity`, `unit_price`, `vat_rate`), and `--output` (PDF path).
  - Optional: `--delivery-date`, `--due`, `--payment-terms`, `--project-ref`, `--notes`, `--cost-note`, `--vat-note`.
  - Multi-line invoices with hours and travel expenses are supported; totals use `Decimal` arithmetic to avoid floating-point rounding errors.
  - factur-x schematron validation runs automatically — clear error messages for EN16931 violations.
  - Raises a descriptive error listing missing fields when required seller or buyer master data is absent.
  - ZUGFeRD XML is embedded via `facturx.generate_from_binary` with `AFRelationship=Alternative` (ZUGFeRD 2.x Comfort profile).

### Fixed

- *(zugferd)* Enforce real PDF/A-3B conformance on `customer-zugferd-create` output: the generated PDF now embeds `pdfaid:part=3` and `pdfaid:conformance=B` XMP metadata markers and a valid sRGB ICC `/OutputIntent` entry. Previously the file lacked these markers and did not pass PDF/A-3B validation.
- *(zugferd)* Fix PaymentMeans `payee_account` Container API usage — crash when vendor has IBAN (`collmex-cli-983`)

### Changed

- *(timing-helper)* `query_timing_entries()`: `hourly_rate` is now a required argument — the 130.0 code default was removed. Billing rates are policy and must be resolved by the caller (invoice skill) from Angebot -> per-customer config -> interactive prompt. Resolves `collmex-cli-47o`.

### Added

- **`customer-invoice` command**: Book outgoing invoices directly in Collmex accounting without the invoicing module (CMXUMS record type). Accepts `--customer-id`, `--invoice`, `--date`, `--net`, `--tax-rate` (default 19%), `--tax` (explicit override), `--text`, and `--account` (revenue account, default 8400).
- **CMXUMS model**: `CustomerInvoice` Pydantic model that serialises to the CMXUMS CSV format, creating a receivable (debtor) entry and an open item for the customer automatically.
- The new command integrates with the existing `open-items --customer` and `bookings` commands: booked invoices appear as open customer items until payment is received and are visible in booking history with debtor and revenue accounts.

### 🚀 Features

- *(invoice-renderer)* Add ReportLab-based PDF renderer for cognovis customer invoices
  - Single-page A4 layout reproducing the cognovis invoice design (logo, header, address block, line-item table, totals)
  - Footer contains all mandatory disclosures: USt-IdNr, HRB/Amtsgericht, IBAN/BIC
  - Handles multiple line items with quantity, unit price, and amount columns
  - Raises `ValueError` on missing mandatory seller fields rather than producing incomplete output
- *(config)* Extend `CollmexConfig` with seller master-data fields (`seller_name`, `seller_street`, `seller_zip`, `seller_city`, `seller_vat_id`, `seller_hrb`, `seller_iban`, `seller_bic`, and optional phone/fax/web/email/bank fields)
  - `seller_configured` property for quick presence check
  - `validate_seller_fields()` returns a list of missing mandatory fields
- *(customer-invoice)* Add travel cost retrieval from MoneyMoney and manual mileage entry
  - `get_moneymoney_travel_costs(category)` calls `mm transactions --category <name> --format json` and returns a list of `TravelCostPosition` objects; raises `MissingCategoryError` if the category is unavailable or the command fails
  - `get_manual_mileage_costs()` prompts interactively for mileage entries (e.g. `2 * 750 km @ 0.38`) or flat amounts (e.g. `570 EUR`) and returns computed `TravelCostPosition` objects; empty input ends entry
  - `get_travel_cost_positions(category)` combines both sources into a single list
  - All error paths (mm unavailable, category not found, JSON parse error) surface as `MissingCategoryError` — no silent data loss
- *(customer-invoice)* Add `TimingHelper` integration to extract billable hours per customer from the Timing app via AppleScript
  - `query_timing_entries(customer, start_date, end_date, hourly_rate)` returns aggregated invoice positions (description, hours, hourly_rate) and a list of unassignable entries
  - Customer assignment resolved via Timing project hierarchy (`Customer/Description` path)
  - Time entries that cannot be attributed to a customer are reported in `unassigned`, not silently discarded
  - An empty period returns an empty positions list with a descriptive notice instead of raising an error

## [2026.03.8] - 2026-03-06

### 🐛 Bug Fixes

- Skip update check for dev versions to fix CI test failures
- *(zugferd)* Swap TaxRegistration schemeID and text to EN 16931 compliance

### 💼 Other

- Backup 2026-03-05 16:02
- Backup 2026-03-05 16:34
- Backup 2026-03-06 04:07
- Bead/ez1/impl — zugferd-create: fix TaxRegistration schemeID/text swap (EN 16931)
## [2026.03.7] - 2026-03-05

### 🚀 Features

- *(cnx)* Add --country flag to vendor-update with overwrite warning

### 💼 Other

- Backup 2026-03-05 15:30
- Bead/cnx/impl — vendor-update: add --country flag with overwrite warning

### ⚙️ Miscellaneous Tasks

- Bump version to 2026.03.7, update changelog
## [2026.03.6] - 2026-03-05

### 🚀 Features

- Vendor-match missing_fields, vendor-update command, zugferd-create validation

### 💼 Other

- Backup 2026-03-05 14:20
- Backup 2026-03-05 14:41
- Backup 2026-03-05 15:04
- Bead/010/impl — ZUGFeRD vendor validation (vendor-match missing_fields, vendor-update, zugferd-create validation)

### ⚙️ Miscellaneous Tasks

- Bump version to 2026.03.6
## [2026.03.5] - 2026-03-05

### 🚀 Features

- Add INVOICE_PAYMENT_GET support with CLI command and Pydantic model

### 🐛 Bug Fixes

- Correct INVOICE_PAYMENT field mapping based on real API response
- Align INVOICE_PAYMENT fully with official API spec

### 💼 Other

- Backup 2026-03-05 06:31
- Bead/4s2/impl — Invoice Payments (INVOICE_PAYMENT_GET)
## [2026.03.4] - 2026-03-05

### 🚀 Features

- *(customer)* Add customer management (CUSTOMER_GET + CMXKND)

### 💼 Other

- Backup 2026-03-05 06:00

### ⚙️ Miscellaneous Tasks

- Add LICENSE, GitHub Actions release workflow, gitignore .playwright-cli
- Bump version to 2026.03.4
## [2026.03.3] - 2026-03-05

### 🚀 Features

- Add ACCBAL_GET account balances support
- Align ACCBAL_GET with official API spec

### 🐛 Bug Fixes

- Correct ACC_BAL field mapping from live API

### 💼 Other

- Bead/8jt/impl — Account Balances (ACCBAL_GET)

### ⚙️ Miscellaneous Tasks

- Bump version to 2026.03.3
## [2026.03.2] - 2026-03-05

### 🚀 Features

- *(invoices)* Add INVOICE_GET support with InvoiceLine/Invoice models, client method, and CLI command

### 💼 Other

- Backup 2026-03-05 05:16
- Backup 2026-03-05 05:32

### ⚙️ Miscellaneous Tasks

- Bump version to 2026.03.1
- Update changelog for v2026.03.2
- Bump version to 2026.03.2
## [2026.03.1] - 2026-03-05

### 🚀 Features

- *(web)* Add bank statement automation with structured status output

### 💼 Other

- Backup 2026-03-04 09:06
- Backup 2026-03-04 14:11
- Backup 2026-03-05 02:52

### ⚙️ Miscellaneous Tasks

- Bump version to 2026.03.0
## [2026.03.0] - 2026-03-04

### 🚀 Features

- ZUGFeRD invoice processing workflow
- *(bank-status)* Add bank-status command with XDG config

### 💼 Other

- Backup 2026-03-02 16:52
- Backup 2026-03-04 06:57
- Backup 2026-03-04 07:15

### ⚙️ Miscellaneous Tasks

- *(beads)* Migrate to dolt backend and configure dolt remote
