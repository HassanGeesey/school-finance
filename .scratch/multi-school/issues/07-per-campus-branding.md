# 07 — Per-campus branding

**What to build:** The Campus owns its identity (UR-14, US-15): name, logo, and contact details, edited by the Campus Admin from the existing settings surface and rendered wherever parents are addressed — receipts, statements, the sidebar brand, tab title, and footer. This is the contract step for the profile: the retired single-row school profile is removed from the model, replaced by the per-Campus profile. The offline path is unchanged in feel — its implicit Campus's profile is what the settings page edits, so a single-school user sees the exact same behavior as today.

**Blocked by:** 03 — Tenant scope plumbing + campus-scoped classes & students.

**Status:** ready-for-agent

- [ ] A Campus Admin edits their Campus's name/logo/contact, saving to that Campus only
- [ ] Receipts, statements, the sidebar, the tab title, and the footer render the acting Campus's identity
- [ ] The single-row school profile is removed from the model; the Campus profile replaces it
- [ ] The offline single-school settings page behaves exactly as today (editing the implicit Campus's profile)
- [ ] Tests: profile service + route tests with two Campuses asserting isolation
