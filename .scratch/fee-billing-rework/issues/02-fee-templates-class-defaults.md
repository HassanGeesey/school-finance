# 02 — Fee templates & class defaults

**What to build:** Fee template management and assignment. Admin creates/edits templates (name + monthly amount). A class carries a default template (replaces the per-class fee-items structure). A template's amount change carries an **effective month** (default next month) and propagates to every linked student from that month (FW-19/FW-20). Templates are Admin-managed (Q24). Audit template creation, edits, and amount changes.

**UI:** Build on the design system (card, form-field, table, modal, toast). A Templates page (list + add/edit, amount edit asks "effective from which month?"), and a template picker on the class edit page (default template). No bespoke markup.

**Blocked by:** 01 — Schema reshape

**Status:** ready-for-agent

- [ ] Create / edit / archive fee templates (name + amount)
- [ ] Template amount change with an effective month
- [ ] Class has a default template; editable
- [ ] Template changes and edits audited
- [ ] Tests: `tests/test_fees_service.py` (+ routes) for template logic

## Comments
