# 05 — Students

**What to build:** Inside a Class, staff add students manually or import them from a CSV. Imported students inherit the class's fee structure. Students can be archived (marked inactive) but never deleted — history and arrears stay. The class page lists its students; a search/filter finds students across classes.

**Blocked by:** 04 — Classes & fee structures

**Status:** implemented

- [x] Add a student manually inside a class
- [x] Import students into a class from a CSV (student fields only); the class is the context
- [x] Import reports what was imported and any rows skipped
- [x] Archive a student (inactive) without deleting; restore possible
- [x] Class page lists students; search finds students across the app
- [x] Student changes are audited

## Comments

Implemented on 2026-08-05 (commit `48bf445`). Business rules live in
`app/students/service.py` (`StudentService`): students are created/updated inside
a class (names required and trimmed); archiving is a status transition
(active -> inactive) that never deletes, and restore is the reverse — unchanged
state produces no audit noise, and updates log old → new names. CSV import is a
single pass: `parse_students_csv` returns `ParsedRow`s carrying physical line
numbers; the first non-blank row is recognised as a header only when its cells
are known header names (bare "first"/"last" are excluded so a student genuinely
named "First Last" is not eaten). Blank rows, missing-name rows, and rows
duplicated within the file are skipped and reported with reasons; the report
shows physical line numbers, and the audit entry records the filename and the
skip count. Imported students inherit nothing at this layer — they become plain
class members, so ticket 06 bills them via the class's fee structure exactly like
manually added students. Search matches first/last/full name case-insensitively
across all classes and includes archived students. Every mutation route is
`require_admin`-gated (403); finance can view. Audit actions
`student_add`/`student_update`/`student_archive`/`student_restore`/
`student_import` were added to `AuditActions` so the log's filter labels them.
Routes are thin adapters (`app/students/routes.py`); the class page gained a
Students section (list, add form, Import CSV link, archive/restore), plus
`app/templates/students/` for search/edit/import/report. Tests:
`tests/test_students_service.py` and `tests/test_students_routes.py`; full suite
191 passed, mypy clean.
