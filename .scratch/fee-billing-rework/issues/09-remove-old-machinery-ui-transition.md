# 09 — Remove old billing machinery & UI transition

**What to build:** Delete everything the compare model replaces and move the UI to the new surface. Remove the Generate button, generation routes/preview, the fee-generation card, per-charge adjustment (extra/waiver) UI, and the class fee-structure editor; the Fees page becomes Templates management (+ closed months link). `app/fees/` service shrinks to the derived account logic; `app/classes/` drops fee-items editing. Sweep the codebase for `Charge`, `GenerationRecord`, `FeeItem`, `Adjustment`, `PaymentAllocation` references (models, services, routes, templates, tests, docs). Full audit-log coverage for new actions (waiver, template edit, amount change, closed month) and removal of stale actions.

**UI:** Navigation reflects the new model — Fees/Templates page, no "Generate fees" anywhere (class page, dashboard quick action, fees page). Empty states updated.

**Blocked by:** 02 — Fee templates & class defaults, 05 — Waivers, 06 — Month-tagged payments & credit, 07 — Student account view, 08 — Reports rewrite

**Status:** ready-for-agent

- [ ] Generate button/UI gone (fees page, class page, dashboard quick action)
- [ ] Class fee-structure editor removed; default-template picker in its place
- [ ] Old routes/partials/actions for generation and adjustments removed
- [ ] No stale `Charge`/`GenerationRecord`/`FeeItem`/`Adjustment`/`PaymentAllocation` references remain
- [ ] Audit actions reflect the new model only
- [ ] Full test suite + mypy green

## Comments
