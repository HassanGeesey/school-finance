# 10 — Arrears

**What to build:** The outstanding-money view. Arrears = a student's unpaid charges minus credits. The report lists each student, how much they owe, and how old the debt is (from their oldest unpaid charge). Archived students and completed classes keep their arrears and still appear. This is the report the office uses to chase unpaid fees.

**UI:** Build on the design system from **05b** — arrears report uses the shared report template; debt age color-coded (amber >30 days, red >60 days).

**Blocked by:** 08 — Payments & receipts, 05b — UI design system & app shell

**Status:** implemented

- [x] Student balance equals charges minus payments minus credits
- [x] Arrears report lists owing students with amount owed and debt age
- [x] Archived students and completed classes still show their arrears
- [x] Students with no outstanding balance are excluded from the report

## Comments

Built via TDD on the service seam (`app/arrears/service.py`), mirroring tickets 06–09.

- `app/arrears/service.py`: `ArrearsService.arrears_report()` — one read-only pass over all charges builds each student's outstanding amount (net of adjustments via `app.fees.service.net_cents`, minus payments cleared via `PaymentAllocation` sums, floored at zero) and their oldest *unpaid* charge period; credits are then subtracted per student and anyone whose arrears are not positive is dropped. Debt age is measured from the oldest unpaid charge's period start (the 1st of its month — stable regardless of when fees were generated), `age_days` is floored at zero, and `debt_age_band()` classifies current (≤30), late (31–60, amber) and overdue (>60, red) per UI-12. Archived students (`StudentStatus.INACTIVE`) and students in Completed/Inactive classes keep their arrears and still appear. Report is ordered by oldest debt first, then amount owed descending.
- `app/arrears/routes.py`: thin adapter — `GET /arrears` (any logged-in user) assembles the summary stats (owing count, total owed, overdue count) and renders the template.
- `app/templates/arrears/index.html`: report page on the 05b design system — `page_header` + three `stat_card`s + the shared `card`/`table_scroll` report template; each row links to the student's account and class, shows student/class status badges (`_badges` from 05/04 features), the owed amount in red, the oldest-debt month, and a `debt_age_badge` (neutral/amber/red — never color alone) from `app/templates/arrears/_badges.html`. Empty state when nobody owes.
- `app/main.py`: `ArrearsService` wired as `app.state.arrears` (read-only, no audit); router mounted. `app/templates/base.html`: the Reports nav group now has a real **Arrears** item (replacing the placeholder) plus a "More reports — Soon" placeholder for ticket 11.
- Tests: `tests/test_arrears_service.py` (17 service tests: balance = charges − payments − credits incl. carried credit offsetting a new charge, amount+age in the report, ordering, archived/completed/inactive kept, fully-paid/credit/never-billed excluded, waivers/extras reflected, age ignores paid charges, band thresholds at 30/60) and `tests/test_arrears_routes.py` (8 route smoke tests incl. login gating, Finance officer access, empty state). Full suite (398 tests) green; mypy clean (34 files).
- Verified manually in-browser against seeded data (chrome-devtools): report sorted oldest-first with correct amounts ($350 total, 4 owing, 3 over 60 days); Geesey shows **Inactive** + **Completed** badges and still owes; a July-only charge shows the amber "31–60 days" band while March/April debts show red "Over 60 days"; empty state renders when nobody owes; Reports nav shows the active Arrears link.

Commit: `5ae45b0`
