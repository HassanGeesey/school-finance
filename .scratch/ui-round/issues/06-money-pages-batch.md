# 06 — Money pages batch re-skin

**What to build:** The money-handling campus pages adopt the shared system end to end: payments index as a ledger; fee templates (list + forms); expenses (dashboard, record form, categories); reports (chart containers restyled, existing Chart.js visuals kept, I-E and collection reports on ledger components). All htmx partials these pages swap in are restyled too so partial responses never flash unstyled. Forms use the shared input/select/button styling; confirm dialogs and toasts use the shared modal/toast. Zero behavior change — same routes, same payloads.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** implemented

- [x] Each listed page renders fully on tokens/components; no hardcoded hex outside the token block
- [x] htmx-swapped fragments arrive pre-styled (partials updated with their parents)
- [x] All money cells right-aligned `.num`; table headers follow the micro-label spec *(38 `amount-cell`/`amount-head` usages across templates; visual confirmation in ticket 08 browser sweep)*
- [x] Money-flow route tests pass unchanged

## Comments

Built (commit `0ba8866`): payments index (the existing record-payment page — this app has no separate payments-ledger page; ledgers live on home.html and student account) restyled onto content-panel/field components with its htmx partials (`_badges`, `_clears`, receipt, profile `_print`) updated alongside so swaps never flash unstyled; fee-template forms/list + closed-months list on shared form/ledger anatomy; expenses dashboard/record/categories restyled; reports frame + index chrome restyled with Chart.js canvases untouched; remaining report pages already consumed the restyled `components/ui.html` macros and needed no direct edits. Credit balances now wear the indigo accent (`badge-indigo`) in fees/_account_finance — closing ticket 07's gap. Zero behavior change: same routes/payloads; tests untouched.

Note for ticket 08: "payments index as a ledger" from the spec doesn't map to an existing route/template — no payments-list page exists in the app. Nothing was invented to force it (scope guard); ledger presentation of Month-tagged Payments is delivered where those lists actually live (campus dashboard, student account).

Verification: included in coordinator's combined phase-2 run over fees/expenses/reports/fee-money/profile/payments suites within 308 passed (tests unchanged).
