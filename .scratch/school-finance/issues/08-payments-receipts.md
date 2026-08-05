# 08 — Payments & receipts

**What to build:** Recording money in. Finance records a payment for a student (amount, method: cash/bank/other). Payments can be partial. A payment clears the oldest unpaid charges first, automatically; any excess becomes a Credit on the student's account. The student's account page shows charges, payments, credits, and the live balance. After each payment a printable receipt is shown (browser-printable HTML). Payment actions are audited.

**Blocked by:** 06 — Monthly fee generation

**Status:** ready-for-agent

- [ ] Record a partial or full payment for a student with amount + method
- [ ] Payment applies to oldest unpaid charges first (per student), one transaction
- [ ] Overpayment becomes a credit automatically
- [ ] Student account page shows charges, payments, credits, and live balance
- [ ] Printable receipt produced per payment
- [ ] Payments are audited
