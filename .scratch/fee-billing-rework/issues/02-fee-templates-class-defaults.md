# 02 — Fee templates & class defaults

**What to build:** Fee template management and assignment. Admin creates/edits templates (name + monthly amount). A class carries a default template (replaces the per-class fee-items structure). A template's amount change carries an **effective month** (default next month) and propagates to every linked student from that month (FW-19/FW-20). Templates are Admin-managed (Q24). Audit template creation, edits, and amount changes.

**UI:** Build on the design system (card, form-field, table, modal, toast). A Templates page (list + add/edit, amount edit asks "effective from which month?"), and a template picker on the class edit page (default template). No bespoke markup.

**Blocked by:** 01 — Schema reshape

**Status:** implemented

- [x] Create / edit / archive fee templates (name + amount)
- [x] Template amount change with an effective month
- [x] Class has a default template; editable
- [x] Template changes and edits audited
- [x] Tests: `tests/test_fees_service.py` (+ routes) for template logic

## Comments

**Built (commit `…`):** fee templates and class defaults on the derived schema.
`app/models.py` adds `Class.default_template_id` (+ `default_template`
relationship), `Student.fee_template_id` (indexed, + `fee_template`
relationship), `FeeTemplate.archived` (soft delete), and the effective-dated
`StudentAmountChange` (student_id, amount_cents, month, year). `app/audit/service.py`
replaces the charge-era actions with `TEMPLATE_CREATE/RENAME/AMOUNT_CHANGE/ARCHIVE/
RESTORE` and `CLASS_DEFAULT_TEMPLATE` (plus the student-schedule actions).

`app/fees/service.py` is `TemplateService` (single testing seam):
create/update/archive/restore/list; an amount edit is effective-dated (default
next month, never past) and `_propagate` writes one `StudentAmountChange` row per
linked student, so a linked student's amount is the last change in force on or
before each month (FW-19/FW-20). `app/fees/routes.py` adapts it (Admin-only,
audited, non-HTMX 303+`?msg=` / HTMX partial + `HX-Trigger` toast).
`app/classes/service.py` gains `set_default_template` (rejects missing/archived
templates; old/new names captured pre-commit for the audit line) and summaries
use the template amount. `app/classes/routes.py` exposes the picker via a
`TemplateOption` dataclass (active templates + the current default when
archived). Templates: fees index/list/form (design-system modal + toast),
class form/detail/index (template picker, "Monthly fee" card, default-template
wording), and the nav label "Fee templates". Stale billing templates deleted
(`_generate_card`, `_preview`, `_adjust_modal`, `_account_finance`).

`app/main.py` is now a pure factory with an `include_billing: bool` toggle: the
mini test app skips the not-yet-reworked billing modules (payments/arrears/
reports still import removed models) and `tests/mini_app.py` builds it against a
temp logo dir. `tests/test_fees_service.py` (33), `test_classes_service.py`,
`test_fees_routes.py`, `test_classes_routes.py` were rewritten against the
`TemplateService`/`ClassService` seam and the mini client, and
`tests/test_schema.py` covers `student_amount_changes`. `app/students/service.py`
(rewritten to link students to templates and seed the baseline amount change at
enrollment) rides along — the propagation story needs it, and its 5 mypy errors
were fixed.

**Verification:**
- Owned tests green: `pytest tests\test_fees_service.py tests\test_classes_service.py
  tests\test_fees_routes.py tests\test_classes_routes.py tests\test_schema.py` →
  **123 passed, 1 warning** (StarletteDeprecationWarning).
- `mypy app\classes app\fees app\students app\audit app\main app\templating` →
  clean.
- **Deliberately still red (expected, later tickets):** the full suite cannot
  even collect — `test_adjustments_*`, `test_arrears_service`,
  `test_payments_planner`, `test_payments_service`, `test_reports_service`
  import removed models; `test_students_service.py` tests the old student API
  (rewritten service, tests not yet ported — student rework ticket). `mypy app`
  still reports the billing modules (`app/payments/routes.py`, `app/reports/
  routes.py`). The billing services (`payments/arrears/reports`, `fees/account.py`)
  are rewritten in the working tree but not committed — they belong to their own
  tickets.
