# 02 — Cloud setup wizard: School + Superadmin

**What to build:** First-run provisioning on the cloud path (UR-17): the setup wizard names the School and creates its Superadmin account in one step, so the School exists with an owner at the top before anything else. There is no operator-side provisioning step. Once any user exists, the wizard is refused. The offline path is unchanged: its wizard still creates the one Admin, bound to the implicit School + Campus from ticket 01, with the same look, fields, and flow. The Superadmin created here can log in and resolves a School-wide scope.

**Blocked by:** 01 — Tenant schema reshape + single-school bootstrap.

**Status:** implemented

- [x] On a fresh cloud deployment, the wizard creates the School (name) and the Superadmin in one step, audited as setup
- [x] Re-running the wizard once any user exists redirects to login
- [x] A Superadmin created this way can log in and is recognized as School-scoped
- [x] The offline single-school wizard still creates the one Admin exactly as before, bound to the implicit Campus
- [x] Tests: service-level (in-memory DB) and route-level (role-authenticated TestClient flows)

## Comments

**Built (commit `d967725`):** first-run provisioning on the cloud path, gated on
`settings.CLOUD_MODE` (I-1: env override `SCHOOL_FINANCE_CLOUD` OR PostgreSQL
`DATABASE_URL` — the offline .exe is always SQLite, so it can never misfire).
`POST /setup` (`app/auth/routes.py`) branches at request time: cloud →
`AuthService.setup_school_superadmin(*, name, username, password, school_name)`
which creates the named `School` + `User(role=SUPERADMIN, school_id=…,
campus_id=None)` in one session (no Campus — the Superadmin creates Campuses
later, ticket 05), audited as `AuditActions.SETUP` with `user=None` and the
school name recorded via `update_profile`; offline → the existing
`setup_first_admin`, now binding the Admin to the implicit School + Campus
(`ensure_bootstrap_on(session)` + `user.school_id`/`user.campus_id` stamps), same
look/fields/flow as before. Shared input validation extracted to
`_validate_setup_inputs()`; the `SetupNotAvailable` gate (wizard refused once any
user exists) is kept on both paths.

**Verification:**
- New tests: `tests/test_auth_service.py` — superadmin creates exactly one
  School, no Campus, correct role/scope/password hash, SETUP audit entry;
  refuses when users exist; requires all fields; offline admin binds to the
  implicit School + Campus. `tests/test_auth_routes.py` — cloud/offline route
  flows via the `CLOUD_MODE` env override.
- Full suite: 666 passed. `mypy` clean (only the pre-existing pystray errors in
  `app/desktop/launcher.py:278` remain).
- `git checkout -- shot-*.png` restored 26 tracked screenshots a sub-agent had
  deleted (environmental, unrelated to this ticket — same as ticket 01).

**Notes for later tickets:** the silent offline bootstrap is now cloud-gated
in the lifespan (`if not settings.CLOUD_MODE: tenants.ensure_bootstrap()`), so a
fresh cloud deployment creates nothing until the wizard runs (UR-17). Campus
creation moves to ticket 05.
