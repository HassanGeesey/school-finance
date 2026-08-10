# 05 — Waivers (charge forgiveness)

**What to build:** Per (student, month) forgiveness. A waiver reduces that month's expected amount by a given amount, floored at $0; multiple waivers stack; a reason/label is required (FW-11). Recordable by Admin **and** Finance officer (FW-13). Waiving a month in full means the student owes $0 for it (used for trivial mid-month partials and skipped months not covered by the closed-month list). Waivers are the only per-month record in the model — no "extras" (FW-12).

**UI:** On the student account page (or via the student), an "Add waiver" action: month picker (pre-filled with an owed month), amount, reason. Waivers list against the month, shown in the account history. Confirmation on create; toast on success.

**Blocked by:** 01 — Schema reshape, 03 — Enrollment & effective-dated amounts, 04 — Owed months & closed months

**Status:** ready-for-agent

- [ ] Add a waiver (student, month, amount, reason) — amount > 0, expected never below $0
- [ ] Multiple waivers stack on a month
- [ ] Reason required; creation audited (who + why)
- [ ] Both Admin and Finance officer can waive
- [ ] Tests: `tests/test_adjustments_service.py` reworked → waiver service tests (+ routes)

## Comments
