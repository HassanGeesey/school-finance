# 04 — Classes & fee structures

**What to build:** The Admin creates Classes and manages each class's itemized fee structure. A Class has a status (Active / Completed / Inactive); Completed/Inactive classes stop generating fees later but keep their records. Each class has fee items (e.g. Tuition, Boarding, Transport, Meals) with monthly prices. All actions are audited.

**Blocked by:** 02 — Setup wizard + auth

**Status:** implemented

- [x] Admin can create, rename, and set the status of a Class
- [x] Admin can add, edit, and remove fee items with prices on a class
- [x] Completed/Inactive classes are visibly marked and can be reopened
- [x] All class/fee-structure changes appear in the audit log
- [x] Finance officer cannot edit classes or fee structures

## Comments

Implemented on 2026-08-05 (commit). Business rules live in
`app/classes/service.py` (`ClassService`): classes are created/updated (name +
status) atomically; fee items are validated (name required, positive integer-cent
amounts, name unique per class mirroring the DB constraint, with an
`IntegrityError` backstop). Add/edit/remove are each audited with the acting user
(updates log old → new values); fee-item mutations verify the item belongs to the
given class. Completed/Inactive classes render a status badge and can be reopened
by selecting Active. Finance can view classes (needed later for fee generation)
but every mutation route is `require_admin`-gated (403). Audit actions
`class_create`/`class_rename`/`class_status`/`fee_item_add`/
`fee_item_update`/`fee_item_remove` were added to `AuditActions` so the log's
filter dropdown labels them. UI: class index + detail pages with an inline fee
item editor and add-item form (`app/templates/classes/`); `money`/`money_input`
template globals format cents; the status-badge label comes from
`CLASS_STATUS_LABELS` (single source). Monthly-fee-per-student totals live in
`ClassService.class_summary`/`list_class_summaries`, keeping the seam intact.
