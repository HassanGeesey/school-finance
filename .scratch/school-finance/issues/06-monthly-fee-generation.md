# 06 — Monthly fee generation

**What to build:** The core billing mechanic. A Finance officer (or Admin) picks a Class or All classes, a Month and Year, clicks Generate — and each student in scope gets one monthly Charge equal to the sum of their class's fee items at that moment (item breakdown snapshotted so later structure edits don't rewrite history). Generation is duplicate-safe per class+month+year: a second attempt is refused, never doubles charges. Completed/Inactive classes are excluded. Generation is audited.

**UI:** Build on the design system from **05b** — use the shared components (card, form-field, button, modal, toast, empty-state) and the grouped sidebar shell. Fee generation = single card (Class/All + Month + Year + Generate), confirm dialog showing the per-class breakdown, duplicate alert via toast/alert, loading state on Generate. No bespoke markup.

**Blocked by:** 05 — Students, 05b — UI design system & app shell

**Status:** ready-for-agent

- [ ] Generate charges for a chosen Class (or All active classes) + Month + Year
- [ ] Each student receives exactly one charge summing their class's fee items
- [ ] Charge stores the item breakdown at generation time
- [ ] Re-generating the same class+month+year is refused (no duplicates), with a clear message
- [ ] Completed/Inactive classes are excluded from "All classes"
- [ ] Generation appears in the audit log
