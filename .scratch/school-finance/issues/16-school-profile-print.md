# 16 — School profile on printed receipts & statements

**What to build:** Printed documents carry the school's identity for parents. Receipts and the printed student statement show the current School name, the Logo (centred, padded), and the contact block — only the non-empty fields from Address, Phone, Email, Website. Reprinting an old document shows the *current* profile, not the one from when it was created.

**Blocked by:** 14 — School profile storage & settings editor

**Status:** implemented

- [x] Printed receipt shows the School name, Logo, and contact block (non-empty fields only)
- [x] Printed student statement shows the same profile block
- [x] Reprinting an old receipt or statement shows the current profile
- [x] With no logo set, the printed documents still show the School name and contact

## Comments

**What was built:**
- Shared macro `print_profile_header(document_label, name, logo, contact)` in `app/templates/profile/_print.html` renders the current school name, centred/padded logo (only when set), and a contact line joined with `·` from the non-empty fields only (address, phone, email, website).
- `app/templates/payments/receipt.html` calls it with `"Fee receipt"`; right side shows Receipt # + paid date.
- `app/templates/students/account.html` gained a `print-only` profile header block (`"Student statement"` with student name + class); the on-screen account page is unchanged.
- `.print-only` utility added in `assets-src/input.css` (`display:none`, block inside `@media print`) and compiled into `app/static/css/app.css` via `npm run build`.
- New global `school_contact()` (`@pass_context`) in `app/main.py` returns the non-empty contact list from the per-request profile.

**Verification:** 5 new tests in `tests/test_profile_routes.py` (receipt/statement identity, non-empty contact filtering, reprint-shows-current-profile). Full suite 576 passed; `mypy app` clean (46 files).

**Commit:** (see git log — implementation + mark commits)
