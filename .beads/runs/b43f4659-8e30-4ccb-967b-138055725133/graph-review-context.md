## Graph Review Context

- provider: codebase-memory
- provider_status: ok
- confidence: high
- routes_in_context: 0

### Changed Files
- .beads/runs/b43f4659-8e30-4ccb-967b-138055725133/evidence_ledger.json
- .beads/runs/b43f4659-8e30-4ccb-967b-138055725133/implementation_manifest.json
- .beads/runs/b43f4659-8e30-4ccb-967b-138055725133/p5-state.json
- library/sussdorff-core/skills/business/customer-invoice/SKILL.md
- library/sussdorff-core/skills/business/customer-invoice/scripts/create_mail_drafts.sh
- library/sussdorff-core/skills/business/customer-invoice/tests/test_create_mail_drafts.py
- src/collmex_cli/api.py
- src/collmex_cli/client.py
- src/collmex_cli/main.py
- tests/test_customer_invoice.py
- tests/test_vendor_features.py

### Relevant Context Files
- src/collmex_cli/api.py
- library/sussdorff-core/skills/business/customer-invoice/SKILL.md
- tests/test_customer_invoice.py
- tests/test_vendor_features.py
- library/sussdorff-core/skills/business/customer-invoice/tests/test_create_mail_drafts.py

### Symbols
- BUCHUNGSNUMMER
- Buchungsnummer
- booking
- response
- field
- skill
- automation
- flows
- bookkeeper
- docs
- request
- create_customer_invoice
- anywhere
- Buchhalters
- Posteingang
- mechanism

### Call Path Symbols
- none

### Evidence Commands
- uv run pytest tests/test_customer_invoice.py::TestCustomerInvoiceCommand::test_buchungsnummer_in_json -v -> exit 1 (RED gate: verify test fails before implementation (AC1 buchungsnummer in customer-invoice JSON))
- uv run pytest tests/test_vendor_features.py::TestVendorInvoiceCommand::test_vendor_invoice_buchungsnummer_in_json -v -> exit 1 (RED gate: verify test fails before implementation (AC2 buchungsnummer in vendor-invoice JSON))
- uv run pytest tests/test_customer_invoice.py::TestCustomerInvoiceCommand::test_missing_new_object_id_errors -v -> exit 1 (RED gate: verify test fails before implementation (AC3 error on missing NEW_OBJECT_ID))
- uv run pytest library/sussdorff-core/skills/business/customer-invoice/tests/test_create_mail_drafts.py::test_passes_buchungsnummer_env -v -> exit 1 (RED gate: verify test fails before implementation (AC4 BUCHUNGSNUMMER env passed to osascript))
- uv run pytest library/sussdorff-core/skills/business/customer-invoice/tests/test_create_mail_drafts.py::test_subject_includes_both_numbers -v -> exit 1 (RED gate: verify test fails before implementation (AC5 bookkeeping subject includes Buchungsnummer))
- uv run pytest tests/test_customer_invoice.py::TestCustomerInvoiceCommand::test_buchungsnummer_in_json -v -> exit 0 (GREEN gate: verify AC1 test passes after implementation)
- uv run pytest tests/test_vendor_features.py::TestVendorInvoiceCommand::test_vendor_invoice_buchungsnummer_in_json -v -> exit 0 (GREEN gate: verify AC2 test passes after implementation)
- uv run pytest tests/test_customer_invoice.py::TestCustomerInvoiceCommand::test_missing_new_object_id_errors -v -> exit 0 (GREEN gate: verify AC3 test passes after implementation)
- uv run pytest library/sussdorff-core/skills/business/customer-invoice/tests/test_create_mail_drafts.py::test_passes_buchungsnummer_env -v -> exit 0 (GREEN gate: verify AC4 test passes after implementation)
- uv run pytest library/sussdorff-core/skills/business/customer-invoice/tests/test_create_mail_drafts.py::test_subject_includes_both_numbers -v -> exit 0 (GREEN gate: verify AC5 test passes after implementation)
- uv run pytest tests/ -v --tb=short -> exit 0 (Full regression: all CLI tests pass with no regressions)
- uv run pytest library/sussdorff-core/skills/business/customer-invoice/tests/ -v --tb=short -> exit 0 (Full regression: all customer-invoice skill tests pass with no regressions)

### Downstream Impacts
- CollmexClient.create_customer_invoice and create_vendor_invoice now return int booking numbers instead of raw API response rows.
- JSON output for invoice booking commands no longer includes the raw response field for these two commands; it includes buchungsnummer.

### Scope Changes
- none

### Skipped Checks
- none
