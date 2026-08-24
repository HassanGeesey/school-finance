# 04 — Record Payment modal + live allocation slip

**What to build:** The record-payment flow becomes prototype's compact modal. Fields: campus (selectable for school-scope users, fixed for campus staff), student select showing monthly rate, integer-cents amount input, target Owed Month select with overdue months marked, payment method select. Below the inputs, a live monospace receipt slip updates as fields change: campus/school header, student, Monthly Amount in force, amount paid, a Credit-rolled-forward row in indigo when overpaying, and a status line — Cleared in full / Partial payment with remaining / Paid in full + credit forwarded. Confirm runs the existing record-payment backend untouched (Month-tagged Payment, Credit rules identical) and surfaces the existing receipt/print outcome; Esc closes without submitting. The modal is openable from any surface that records payments today.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** implemented

- [x] Slip previews partial-remaining, cleared, and credit-forwarded states correctly for chosen student/amount
- [x] Submitted payments hit the existing endpoints; amounts, tagged month, method persist exactly as before
- [x] Receipt generation/print behavior unchanged
- [x] Esc cancels cleanly; no submission on close
- [x] Existing payment route tests pass unchanged

## Comments

-

Built: `record.html` is now a compact host page (student summary board + trigger button) that auto-opens the new self-contained `_record_modal.html` `<dialog>` on load. The modal holds campus (fixed to acting campus; editable only when a caller passes options + flag), student select showing monthly rate ("Ada Lovelace — $50.00/mo"), decimal-dollar amount input mapped to integer cents, Owed Month select built from `account.lines` (overdue = past month still carrying shortfall, marked "· overdue", JS-synced year select), method select, payment date. Below the inputs a live monospace `.receipt-slip` recomputes on every keystroke/change from server-rendered line data: campus/school header + contact, student, Owed month, Monthly Amount in force, Amount paid, indigo "Credit rolled forward" row on overpay, and one status of Cleared in full / Partial payment — remaining X / Paid in full + credit forwarded. Form posts the identical fields (`student_id`, `amount`, `method`, `paid_on`, `month`, `year`) to `/payments/record`; success redirect and receipt/print flow untouched; POST-error re-render reopens the modal with the in-modal error alert. Esc / ✕ / backdrop / Cancel close without submitting via ui.js declarative hooks; no JS files touched.

Verification: `.venv\Scripts\python.exe -m pytest tests/test_payments_routes.py tests/test_fee_money_routes.py -q -p no:warnings` → 30 passed. Extra throwaway render check confirmed dialog markup, FW-22-1 default-tag `value="N" selected` contract, JSON slip data, and owed-month data attributes on the rendered page (file deleted after).

Not committed — task instruction forbids git commands for this session.

Coordinator note: implementation committed as `0463acd`; included in the 308-passed combined phase-2 run. Open nuance for ticket 05/08: school-scope campus retargeting inside the modal awaits backend support (no campus field on POST /payments/record today) — modal currently fixed to the acting campus, which matches today's behavior.
