# 15 — School profile in the setup wizard & app shell

**What to build:** The school's identity shows up where staff see it day-to-day. The first-run setup wizard collects the required School name. The sidebar brand block, browser tab title, and footer show the School name instead of the product name, with the Logo shown centred and padded in the brand block (falling back to the default icon when none is set). The setup wizard and login screens keep the product name "School Finance" — they are about the software, not the school.

**Blocked by:** 14 — School profile storage & settings editor

**Status:** implemented

- [x] Setup wizard collects a required School name on first run
- [x] Sidebar brand shows the School name and Logo (centred, padded, overflow-safe); default icon when no logo is set
- [x] Browser tab title and footer show the School name
- [x] Setup wizard and login screens keep the product name "School Finance"

## Comments

**What was built:**
- `app/main.py`: per-request `request.state.school_profile` plus `@pass_context` globals `school_name()` and `logo_url()` (with `school_contact()` for ticket 16); logo served from `/logos/{filename}`.
- `app/templates/base.html`: sidebar brand block shows `school_name()` with the logo centred/padded/overflow-safe and the default icon fallback; browser tab title and footer use the school name. All logged-in templates switched from `{{ app_name }}` to `{{ school_name() }}` for titles.
- Setup wizard (`app/templates/auth/setup.html` + `app/auth/routes.py`/`service.py`) collects the required School name on first run; setup and login keep the product name "School Finance".
- `.scratch/.../16` test-file additions cover setup/login product name retention and dashboard school-name rendering.

**Verification:** `tests/test_profile_routes.py` app-shell tests (school name in shell/title, product name on setup/login). Full suite 576 passed; `mypy app` clean.


**Commit:** e37229e (implementation); ticket mark included in same commit
