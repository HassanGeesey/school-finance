# Fee billing rework — spec

Reshape fee billing to **bill from enrollment**: no generation step, no charge rows.
A student's obligation is derived from their enrollment, and payments are compared per month.

Governing goal (user): **as simple and useful as possible**. Decisions log: `project-decisions.md` → "Fee workflow grilling session" (FW-1..FW-22). Terms: `CONTEXT.md` → "Fee billing".

## Model

- **Fee Template** — name + monthly amount. A class has a default template; a student is linked to a template or holds a custom amount.
- **Student** — gains `enrolled_on` (first owed month) and `archived_on` (last owed month, captured on archive). Monthly amount is **effective-dated**: an amount change carries an effective month (default next month); a month's expected uses the amount in force for that month. Template raises propagate to linked students from the change's effective month.
- **Owed month** — from `enrolled_on` month through the archive month (service-through-period-end), excluding **closed months**, while active. First month is full (no proration).
- **Closed Month** — school-wide list; excluded from every student's owed months; never appears as unpaid.
- **Waiver** — per (student, month), reduces that month's expected, floor $0, reason required, stackable. Recordable by Admin and Finance officer.
- **Payment** — gains a month+year tag; any month may be tagged. **Excess rolls forward as credit**, consumed by the oldest owed months' shortfalls first (visible per month).
- **Expected vs paid** — per owed month: `expected = amount in force − waivers (min $0)`; status = paid/partial/unpaid vs payments tagged to the month plus credit applied.

## Removed

`Charge`, `Adjustment`, `GenerationRecord`, `FeeItem`, `PaymentAllocation`; the Generate button/page; per-charge adjustments UI; class fee-structure editing. No data migration (nothing real yet, FW-18). `Credit` stays.

## Derived reports

- Paid/unpaid per month — every student with an owed month in the selected period, closed months excluded.
- Arrears — sum of monthly shortfalls, age-banded by month.
- Income vs expense — unchanged (payments by date).
