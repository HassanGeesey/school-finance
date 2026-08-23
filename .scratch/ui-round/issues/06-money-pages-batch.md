# 06 — Money pages batch re-skin

**What to build:** The money-handling campus pages adopt the shared system end to end: payments index as a ledger; fee templates (list + forms); expenses (dashboard, record form, categories); reports (chart containers restyled, existing Chart.js visuals kept, I-E and collection reports on ledger components). All htmx partials these pages swap in are restyled too so partial responses never flash unstyled. Forms use the shared input/select/button styling; confirm dialogs and toasts use the shared modal/toast. Zero behavior change — same routes, same payloads.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** ready-for-agent

- [ ] Each listed page renders fully on tokens/components; no hardcoded hex outside the token block
- [ ] htmx-swapped fragments arrive pre-styled (partials updated with their parents)
- [ ] All money cells right-aligned `.num`; table headers follow the micro-label spec
- [ ] Money-flow route tests pass unchanged

## Comments

-
