# Agent Instructions

Use hosted issues through `ccore tracker`. Refer to issues as `owner/repo#N`.

## Skill Dependencies

### customer-invoice (sussdorff-core)

The `customer-invoice` skill lives in:
`/Users/malte/code/library/sussdorff-core/skills/business/customer-invoice/`

It provides travel cost collection used by the invoice-composition pipeline:

- `scripts/travel_costs.py` — `get_travel_cost_positions(customer_category, **kwargs)`
  combines MoneyMoney category transactions (`mm transactions --category`) with
  interactive manual mileage entry into a unified `TravelCostPosition` list.
- Category convention: `Reisekosten/<customer>` in MoneyMoney (e.g. `Reisekosten/cognovis`)
- Raises `MissingCategoryError` if the category is not found — never silently drops entries.

Run skill tests:
```bash
cd /Users/malte/code/library/sussdorff-core/skills/business/customer-invoice
uv run pytest tests/test_travel_costs.py -v
```

## Quick Reference

Read work with `ccore tracker show cognovis/collmex-cli#N`.

## Session Completion

Use the installed session-close skill and `ccore session-close` in the active
delivery session after required verification and review. The CLI owns integration,
Issue finalization, synchronization, memory and cleanup for the exact supplied
resources. Do not run a parallel manual completion recipe. Resume a typed
retryable stop using its Session Close ID; publication awaiting human review
is not terminal completion. Report the CLI result and any project-specific
postconditions. Preserve existing authorization for the same concrete scope.
