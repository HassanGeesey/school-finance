# 0002 — Bill from enrollment: the month-tagged compare model (no charges, no generation)

**Status:** accepted

Fee billing is derived, not generated. There is no monthly "Generate fees" button, no `Charge` rows, no generation records, and no duplicate-safety. A student is expected to pay their Monthly Amount for every **owed month** — from their `enrolled_on` month through the month they leave (service-through-period-end), excluding school-wide **closed months** — and a payment is simply recorded against a month. The system **compares** each month's expected amount (amount in force minus waivers) against the payments tagged to that month, producing paid/partial/unpaid; any excess rolls forward as **credit** toward the oldest owed months first.

The trigger that closed the hole: a student enrolled after the old per-class "generation" step had no charge at all, so their balance read $0 and they never appeared in "who didn't pay this month". Because being enrolled *is* the billing here, that hole cannot exist — you cannot enroll without starting to owe.

## Considered options

- **Keep monthly generation and patch the hole** — auto-create a charge when a student joins a class that already generated. Rejected: two ways charges come into existence, the manual ritual stays, and the duplicate-safety machinery stays. Shallow simplification.
- **Auto-bill on enrollment with charge rows kept** (FW-4) — enrollment creates a charge row per month. Rejected during grilling in favour of the even simpler compare model (FW-5): the expected amount (the student's monthly amount) already defines each month's obligation, so per-month charge rows add machinery without adding information.
- **Record payments with no expected amount at all** (FW-2) — rejected: "paid anything?" is answerable but "paid the right amount?" is not, and untethered payments have no month to attach to.

## Consequences

- Amount changes are **effective-dated** (from a chosen month, default next month), so past months never rewrite — "Paid for March" can't change because fees rose in July. This is the price of the live, single-amount model: history must be frozen by convention rather than by charge rows.
- The payment's month tag is the clerk's entry, not system-enforced allocation; guardrails (show oldest unpaid month first, warn on out-of-range months) mitigate mis-tagging.
- Reports (paid/unpaid per month, arrears as accumulated shortfalls) are derived from the comparison, so they are as-of the current amounts in force.
