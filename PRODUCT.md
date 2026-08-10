# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A single school's admin/secretary, working at one desk — either the office PC (packaged Windows .exe) or a locally served web app. Their daily job: keep the school's money flows in order — generate monthly fees, record payments and expenses, and chase arrears. A Finance officer role records payments/expenses and generates fees; the Admin owns structure, users, and settings. Same desk, same daily rhythm.

## Product Purpose

Run one real school's finances end-to-end: fee structures per class, one-click monthly fee generation, per-student adjustments, payment recording with printable receipts, expense recording, arrears tracking, reports with CSV export, and a complete audit trail. Success means the school's month-end numbers are correct, complete, and explainable.

## Positioning

A self-contained, single-machine finance app for one real school. No accounts, no cloud dependency, no setup beyond first launch. Charge history is snapshotted at generation time and every meaningful action is audited, so the books are defensible and the workflow is simple.

## Operating Context

- One desk, one machine; app served on localhost (packaged Windows .exe with tray icon) or via Docker at ict.hgeesey.store.
- Two roles log in with staff accounts; server-side sessions; PBKDF2 password hashing.
- Manual monthly billing rhythm: a staff member clicks "generate" once per class+month.
- Printed receipts and student statements carry the school's own name, logo, and contact block, rendered at print time from the current profile.

## Capabilities and Constraints

- Classes (Active / Completed / Inactive) with itemized monthly fee structures; students added manually or imported via CSV; archive instead of delete.
- Monthly fee generation is duplicate-safe per class+month+year; the item breakdown is snapshotted so later structure edits never rewrite history.
- Per-student extras/waivers (Admin-only); waivers never drive a charge below zero.
- Payments: partial payments clear oldest unpaid charges first; overpayment becomes credit; printable receipt per payment.
- Expenses against Admin-managed categories, with cash/bank/other method.
- Reports with CSV export; arrears by age; dashboard charts.
- Full audit log; automatic backup on startup plus manual "Backup now", keeping ~30 copies.
- USD, English. Money stored in integer cents. SQLite single file, env-driven data directory.
- Two roles only: Admin and Finance officer.

## Brand Commitments

- The software is called "School Finance"; the school's own name, logo, and contact details appear in the app shell and on printed documents.
- Visual: must stay light and professional (confirmed 2026-08-09). No other binding brand constraints.

## Evidence on Hand

- CONTEXT.md glossary (School Name vs App Name), README feature list, project-decisions.md decision log, `.scratch/school-finance/spec.md` and 18 implemented tickets.
- Live deployment at ict.hgeesey.store (outcome recorded in project-decisions.md, 2026-08-07).

## Product Principles

- **Money truth is sacred:** history is immutable (snapshotted charges), every mutation is audited, and numbers must never be misread.
- **One desk, one person:** the daily flow (generate → collect → record → chase) takes the fewest clicks and zero head-scratching.
- **Restraint earns trust:** a calm, light, professional surface where structure and the numbers themselves carry the weight.
- **Roles keep the school safe:** structure and system mutations are Admin-gated; Finance moves money day-to-day.
