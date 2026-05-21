## [Unreleased]

### 🚀 Features

- *(invoice-renderer)* Add ReportLab-based PDF renderer for cognovis customer invoices
  - Single-page A4 layout reproducing the cognovis invoice design (logo, header, address block, line-item table, totals)
  - Footer contains all mandatory disclosures: USt-IdNr, HRB/Amtsgericht, IBAN/BIC
  - Handles multiple line items with quantity, unit price, and amount columns
  - Raises `ValueError` on missing mandatory seller fields rather than producing incomplete output
- *(config)* Extend `CollmexConfig` with seller master-data fields (`seller_name`, `seller_street`, `seller_zip`, `seller_city`, `seller_vat_id`, `seller_hrb`, `seller_iban`, `seller_bic`, and optional phone/fax/web/email/bank fields)
  - `seller_configured` property for quick presence check
  - `validate_seller_fields()` returns a list of missing mandatory fields

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
