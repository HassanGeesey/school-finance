# 02 — Cloud setup wizard: School + Superadmin

**What to build:** First-run provisioning on the cloud path (UR-17): the setup wizard names the School and creates its Superadmin account in one step, so the School exists with an owner at the top before anything else. There is no operator-side provisioning step. Once any user exists, the wizard is refused. The offline path is unchanged: its wizard still creates the one Admin, bound to the implicit School + Campus from ticket 01, with the same look, fields, and flow. The Superadmin created here can log in and resolves a School-wide scope.

**Blocked by:** 01 — Tenant schema reshape + single-school bootstrap.

**Status:** ready-for-agent

- [ ] On a fresh cloud deployment, the wizard creates the School (name) and the Superadmin in one step, audited as setup
- [ ] Re-running the wizard once any user exists redirects to login
- [ ] A Superadmin created this way can log in and is recognized as School-scoped
- [ ] The offline single-school wizard still creates the one Admin exactly as before, bound to the implicit Campus
- [ ] Tests: service-level (in-memory DB) and route-level (role-authenticated TestClient flows)
