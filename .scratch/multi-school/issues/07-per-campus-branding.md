# 07 — Per-campus branding

**What to build:** The Campus owns its identity (UR-14, US-15): name, logo, and contact details, edited by the Campus Admin from the existing settings surface and rendered wherever parents are addressed — receipts, statements, the sidebar brand, tab title, and footer. This is the contract step for the profile: the retired single-row school profile is removed from the model, replaced by the per-Campus profile. The offline path is unchanged in feel — its implicit Campus's profile is what the settings page edits, so a single-school user sees the exact same behavior as today.

**Blocked by:** 03 — Tenant scope plumbing + campus-scoped classes & students.

**Status:** implemented

- [x] A Campus Admin edits their Campus's name/logo/contact, saving to that Campus only
- [x] Receipts, statements, the sidebar, the tab title, and the footer render the acting Campus's identity
- [x] The single-row school profile is removed from the model; the Campus profile replaces it
- [x] The offline single-school settings page behaves exactly as today (editing the implicit Campus's profile)
- [x] Tests: profile service + route tests with two Campuses asserting isolation

## Comments

Built: `SchoolProfile` is removed from the model. `ProfileService` now resolves
the Campus it operates on from the request scope (`_campus_for`) — a
Campus-bound role edits exactly its own Campus — or from an explicit `campus`
argument for non-request contexts. The middleware resolves
`request.state.campus_profile` inside the scope context, and the shell globals
(`school_name`, `logo_url`, `school_contact`) read it, so the sidebar brand,
tab title, footer, receipts, and statements render the acting Campus's identity
(School-bound scopes with no Campus fall back to the product name). The offline
setup wizard names the implicit Campus (`setup_first_admin` passes it to
`update_profile`); the cloud superadmin path no longer touches the profile —
the School row holds its name. `scripts/seed_demo.py` bootstraps the implicit
Campus and binds the demo admin to it.

Verification: rewritten `tests/test_profile_service.py` (scope resolution,
edit/audit rules, logo lifecycle, two-Campus isolation), updated
`tests/test_profile_routes.py` (setup names the implicit Campus, per-Campus
route isolation, app-shell shows acting Campus, cross-campus logo isolation),
`tests/test_auth_service.py` and `tests/test_schema.py` updated for the retired
model. Full suite green (804 tests); `mypy app` clean.

Commit: `d73406a`
