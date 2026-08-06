# 08 — Payments & receipts

**What to build:** Recording money in. Finance records a payment for a student (amount, method: cash/bank/other). Payments can be partial. A payment clears the oldest unpaid charges first, automatically; any excess becomes a Credit on the student's account. The student's account page shows charges, payments, credits, and the live balance. After each payment a printable receipt is shown (browser-printable HTML). Payment actions are audited.

**UI:** Build on the design system from **05b** — use shared components; record-payment screen = search student with live balance → amount/method → confirmation line → save → toast + print receipt; student account page = header with big color-coded balance, expandable charges with items/adjustments, payments list, balance footer; print-ready receipt uses the print CSS from 05b.

**Blocked by:** 06 — Monthly fee generation, 05b — UI design system & app shell

**Status:** implemented

- [x] Record a partial or full payment for a student with amount + method
- [x] Payment applies to oldest unpaid charges first (per student), one transaction
- [x] Overpayment becomes a credit automatically
- [x] Student account page shows charges, payments, credits, and live balance
- [x] Printable receipt produced per payment
- [x] Payments are audited

## Comments

Built via TDD on the service seam (`app/payments/service.py`), mirroring tickets 06/07.

- `app/payments/service.py`: `PaymentService` — `record_payment()` validates amount (positive integer cents via `app.money`), method (cash/bank/other, `PaymentMethods`), and date (parsable, not in the future), then in one transaction applies the payment to the student's oldest unpaid charges first (year/month/id order, skipping settled charges, partial application supported). Any excess becomes a `Credit` linked to the payment. `student_account()` returns `StudentAccount` (charges with paid/remaining + paid/partial/unpaid status, payments, credits, live balance = outstanding − credits), `get_payment()` loads the receipt data, `list_recent_payments()` feeds the payments page. Every recorded payment writes one audit entry; a rejected payment writes nothing.
- `app/payments/routes.py`: thin adapters — `GET /payments` (search student with live balance + recent payments), `GET/POST /payments/record` (record form → redirect to receipt; errors re-render the form with the reason, 400), `GET /payments/{id}/receipt` (printable). Any logged-in user (incl. Finance officer) may view and record.
- `app/audit/service.py`: new `PAYMENT_RECORD` action + "Payment recorded" label.
- Templates: `payments/index.html`, `payments/record.html`, `payments/receipt.html` (browser-printable via the 05b print CSS), `payments/_badges.html` (method + charge-status badges); `fees/_account_finance.html` extended with payments list, credits, status badges, and a balance footer; "Record payment" action on `students/account.html`; Payments nav item replaces the placeholder in `base.html`.
- `app/main.py`: `PaymentService` wired as `app.state.payments`; router mounted.
- Tests: `tests/test_payments_service.py` (23 service tests) and `tests/test_payments_routes.py` (14 route smoke tests) added. Full suite (194 tests) green; mypy clean.
- Verified manually in-browser: record → toast → printable receipt showing allocations + credit, account page balance/statuses, audit entries with credit mention.

Commit: `eac3914`

### Code-review fixes

Post-review polish addressing the two-axis code review of the ticket:

- **Audit atomic with the payment.** `AuditService.add(session, ...)` added; `record_payment()` now writes its `PAYMENT_RECORD` entry inside the same transaction as the payment/allocations/credit, so a failed audit rolls the whole payment back (`log()` still works standalone). New test `test_an_audit_failure_rolls_back_the_whole_payment`.
- **Confirmation line (spec UI).** New `PaymentService.preview_application()` (write-free, oldest-first) + `ApplicationPreview`; `GET /payments/preview` htmx fragment; the record form's amount input triggers a live "what this payment clears" preview (per-charge applied amounts + credit line).
- **Toast on save.** Receipt page now fires the app's toast via a new `body_end` block in `base.html` instead of an inline alert; verified in-browser.
- **Single-source helpers.** `period_label()`, `net_cents()`, `to_charge_line()` moved to module level in `app/fees/service.py`; `AdjustmentsService` and `PaymentService` both delegate (previously three copies of the period label and two of the net computation). N+1 payment-application loop collapsed to one `_paid_cents_by_charge()` lookup; redundant `except (PaymentError, InvalidMethod, InvalidDate)` narrowed to `except PaymentError`.
- Tests: 7 new service tests + 3 route tests; full suite now 321 tests green; mypy clean (28 files).

Commit: `1e55c3c` (follow-up, review fixes)

