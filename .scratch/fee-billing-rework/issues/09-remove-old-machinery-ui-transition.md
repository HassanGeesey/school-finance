# 09 — Remove old billing machinery & UI transition

**What to build:** Delete everything the compare model replaces and move the UI to the new surface. Remove the Generate button, generation routes/preview, the fee-generation card, per-charge adjustment (extra/waiver) UI, and the class fee-structure editor; the Fees page becomes Templates management (+ closed months link). `app/fees/` service shrinks to the derived account logic; `app/classes/` drops fee-items editing. Sweep the codebase for `Charge`, `GenerationRecord`, `FeeItem`, `Adjustment`, `PaymentAllocation` references (models, services, routes, templates, tests, docs). Full audit-log coverage for new actions (waiver, template edit, amount change, closed month) and removal of stale actions.

**UI:** Navigation reflects the new model — Fees/Templates page, no "Generate fees" anywhere (class page, dashboard quick action, fees page). Empty states updated.

**Blocked by:** 02 — Fee templates & class defaults, 05 — Waivers, 06 — Month-tagged payments & credit, 07 — Student account view, 08 — Reports rewrite

**Status:** implemented

- [x] Generate button/UI gone (fees page, class page, dashboard quick action)
- [x] Class fee-structure editor removed; default-template picker in its place
- [x] Old routes/partials/actions for generation and adjustments removed
- [x] No stale `Charge`/`GenerationRecord`/`FeeItem`/`Adjustment`/`PaymentAllocation` references remain
- [x] Audit actions reflect the new model only
- [x] Full test suite + mypy green

## Comments

Most of the old machinery was already gone (tickets 02–08 removed models, generation routes/partials, per-charge adjustment UI, and the class fee-structure editor; `app/audit/service.py` already carried only new-model actions). This ticket swept the residue:

- **Last Generate quick action:** `app/templates/home.html` "Generate fees" button removed; nothing else on the dashboard refers to generation. Class page uses the default-template picker; fees page is templates + closed months.
- **Stale copy replaced:** audit log subtitle, record-payment page ("clears the oldest unpaid months"), receipt ("covers the month(s) listed above"), arrears stat ("Expected minus paid and credit"), class archive confirm, class-inactive note, and the import-student billing line ("uses this class's default fee template").
- **Naming:** `allocation_rows` context key renamed `applied_rows` (route + receipt template); module docstrings swept (`app/fees/__init__.py`, `app/audit/service.py`, `app/reports/service.py`, `app/classes/__init__.py`). README.md/PRODUCT.md updated to the derived model.
- **Mypy:** fixed the pre-existing `app/students/routes.py:218` error (narrow `assert template_id is not None` — both-None returns early, so the `set_template` branch guarantees it); `mypy app` is now clean across all 51 files.
- **Judgement call — `ChargeStatus` kept:** `app/charge_status.py` (`ChargeStatus` + labels/tones) is the *new-model* paid/partial/unpaid classifier used by account, reports, and students — not the removed `Charge` row. Its "Charge"-prefixed name is cosmetic; renamed for clarity only if desired. The only remaining "charge"/"fee structure" matches in app/ are intentional: `charge_status.py` (classifier), "no charge rows / replaced charge rows" historical docstrings, and the schema test asserting old tables are removed.
- **Verification:** full `pytest tests/` → 629 passed, exit 0. `mypy app` → no issues in 51 source files.
- **Commit:** `9257300`.
