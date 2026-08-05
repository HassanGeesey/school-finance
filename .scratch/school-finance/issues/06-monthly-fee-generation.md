# 06 — Monthly fee generation

**What to build:** The core billing mechanic. A Finance officer (or Admin) picks a Class or All classes, a Month and Year, clicks Generate — and each student in scope gets one monthly Charge equal to the sum of their class's fee items at that moment (item breakdown snapshotted so later structure edits don't rewrite history). Generation is duplicate-safe per class+month+year: a second attempt is refused, never doubles charges. Completed/Inactive classes are excluded. Generation is audited.

**UI:** Build on the design system from **05b** — use the shared components (card, form-field, button, modal, toast, empty-state) and the grouped sidebar shell. Fee generation = single card (Class/All + Month + Year + Generate), confirm dialog showing the per-class breakdown, duplicate alert via toast/alert, loading state on Generate. No bespoke markup.

**Blocked by:** 05 — Students, 05b — UI design system & app shell

**Status:** implemented

- [x] Generate charges for a chosen Class (or All active classes) + Month + Year
- [x] Each student receives exactly one charge summing their class's fee items
- [x] Charge stores the item breakdown at generation time
- [x] Re-generating the same class+month+year is refused (no duplicates), with a clear message
- [x] Completed/Inactive classes are excluded from "All classes"
- [x] Generation appears in the audit log

## Comments

Implemented on 2026-08-05. Business rules live in
`app/fees/service.py` (`FeeService`): `preview()` computes the per-class
breakdown for the confirm dialog, `generate()` creates one `Charge` per active
student summing the class's fee items with the item breakdown snapshotted into
`Charge.breakdown`, and writes a `GenerationRecord` per class+month+year so a
second attempt is refused (raises `AlreadyGenerated`) and "All classes" re-runs
skip already-billed classes. Only Active classes generate; a class with no fee
items is refused/skipped (`NoFeeItems`); archived students accrue no new charges.
Period validation (`InvalidPeriod`) enforces month 1-12 and year 2000-2100.
Every generation that creates anything is audited under `FEE_GENERATE`. Routes
(`app/fees/routes.py`) are thin HTMX adapters: `/fees` (card page),
`/fees/preview` (confirm-dialog partial `fees/_preview.html`),
`/fees/generate` (swaps the card + toast). Any logged-in user (Admin or Finance
officer) can generate; the fees page lists Active classes with their monthly fee
and shows an empty state when none exist. Verified by the full suite (service +
route tests) and mypy.

Commit: `2978a0e`

