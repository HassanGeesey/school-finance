# 14 — School profile storage & settings editor

**What to build:** The foundation for the school's identity. A single-row `school_profile` record holds the required School name and optional contact details (Address, Phone, Email, Website) plus the uploaded Logo filename. An Admin edits all of it from a new "School profile" card on the Settings page — the school name can never be blank, contact fields are free text, and every change (including logo upload and removal) is written to the audit log.

**Blocked by:** None — can start immediately (the Settings page from 12 and the design system from 05b are already in place)

**Status:** implemented

- [x] A single-row school profile exists in the database (school name required; address, phone, email, website, logo filename optional)
- [x] Settings page shows a "School profile" card where an Admin can view and edit the profile
- [x] Saving with an empty school name is refused; contact fields accept any text
- [x] Logo upload accepts an image, stores the file next to the app data, and records the filename; a "Remove logo" action clears it
- [x] Every edit, upload, and removal is written to the audit log
- [x] Only Admin can reach it (the Settings page is already Admin-only)

## Comments

**What was built:**
- `app/profile/service.py`: `SchoolProfile`-backed `ProfileService` with `get_profile()`, `update_profile()`, `upload_logo()`, `remove_logo()`; `LogoStorage` stores files under the data directory (`logo_dir`) with magic-byte guards for PNG/JPEG/GIF/WebP; school name can never be blank; every mutation writes to the audit log via new `AuditActions.PROFILE_UPDATE`, `PROFILE_LOGO_UPLOAD`, `PROFILE_LOGO_REMOVE`.
- `app/profile/routes.py` (mounted at `/profile`): HX-POST `/profile` (HTMX partial refresh) and `/profile/logo`, plus `/profile/logo/remove`; the partial `app/templates/profile/_profile.html` card lives on the Settings page (`app/templates/admin/index.html`).
- Setup wizard creates the initial profile (`setup_first_admin(school_name=...)`); school name is required on first run.

**Verification:** `tests/test_profile_service.py` + `tests/test_profile_routes.py` cover update/validation/audit/logo upload & removal/setup wiring. Full suite 576 passed; `mypy app` clean.


**Commit:** e37229e (implementation); ticket mark included in same commit
