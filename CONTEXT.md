# School Finance App

A single-machine finance app for one real school: fee collection, expenses, and arrears tracking. Admin and Finance officer roles.

## Language

**School Name**:
The name of the real school the app runs for (e.g. "Sunrise Primary School"). It is configurable in Settings and appears wherever parents or printed documents are addressed — receipts, the sidebar brand, tab titles, and the footer.
_Avoid_: System name, App name

**App Name**:
The product name of the software itself, fixed as "School Finance". It is the software's identity (setup wizard, Settings page context) and is never the school's name.
_Avoid_: Program name, Software name

**School Profile**:
The school's identity as shown to parents and on printed documents: the School Name, the Logo, and the Contact Details. Configured by an Admin in Settings, collected on first launch (name only), stored as a single row in the database, and rendered live at print time.
_Avoid_: Branding, Settings, System configuration

**Logo**:
An image file representing the school, uploaded by an Admin. It lives as a file next to the app data (not in the bundled static assets) and shows centred in the sidebar brand and at the top of printed receipts. Falls back to the default icon when absent.
_Avoid_: Icon, Picture, Brandmark

**Contact Details**:
The optional free-text contact block of the School Profile — Address, Phone, Email, and Website. No validation; blank fields simply do not display on printed documents.
_Avoid_: Contact info, Contact fields, Details

## Fee billing

**Fee Template**:
A named monthly amount (e.g. "Standard — $100") a class defaults to and a student can be linked to. It defines what a student is expected to pay each month.
_Avoid_: Fee type, fee plan, fee structure, fee items

**Monthly Amount**:
What a student is expected to pay per month — the amount of their linked Fee Template, or a custom amount. One amount in force at a time; changes are effective from a chosen month.
_Avoid_: Fee, tuition fee, charge amount

**Amount in Force**:
The Monthly Amount that applies to a given month, determined by the student's effective-dated amount changes. Past months keep the amount that was in force then — a later change never rewrites them.
_Avoid_: Current amount, live amount

**Enrollment Date**:
The day a student started attending. The month of this date is their first owed month.
_Avoid_: Start date, created date, registered date

**Owed Month**:
Any month a student is expected to pay for: from their Enrollment Date's month through the month they leave (service-through-period-end), excluding Closed Months, while active.
_Avoid_: Charge month, billing month, term month

**Expected Amount**:
For a given owed month, what the student should pay: the Amount in Force for that month minus any Waivers, never below zero.
_Avoid_: Charge, fee amount, balance due

**Waiver**:
A per-(student, month) forgiveness that reduces that month's Expected Amount, with a required reason. Multiple waivers can stack on one month.
_Avoid_: Adjustment, discount, extra, concession

**Closed Month**:
A month the whole school is closed (e.g. a holiday). No student owes it; it is excluded from every student's owed months and never appears as unpaid.
_Avoid_: Holiday, blackout date, skipped month

**Month-tagged Payment**:
A payment recorded against a specific month; the expected-vs-paid comparison happens per month. Any month can be tagged.
_Avoid_: Allocation, payment for, unallocated payment

**Credit**:
Money a parent has paid beyond what was owed. It rolls forward and covers the oldest owed months' shortfalls first.
_Avoid_: Overpayment, credit balance, refund, advance
