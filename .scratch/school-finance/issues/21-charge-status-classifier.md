# 21 — One ChargeStatus, one classifier

**What to build:** "paid / partial / unpaid" is one enum with one classifier and one tone map, owned by one module. The student account, reports, and lists all read from it instead of each re-deriving status and color.

**Blocked by:** None — can start immediately

**Status:** implemented

- [x] A single status enum replaces the twin definitions
- [x] Classification (given amounts, compute status) and status tones are defined once and used by both account and report rendering
- [x] Route files no longer compute status or tones
- [x] Tests stay green; classifier tested once

## Comments

Implemented 2026-08-08. New module `app/charge_status.py` owns the whole concept: `ChargeStatus` (paid/partial/unpaid), `CHARGE_STATUS_LABELS`, `CHARGE_STATUS_TONES`, and the single classifier `classify_paid_status(net_cents, paid_cents)`. The twin definitions are gone — `ChargeStatus` removed from `app/payments/service.py` and `PaidStatus`/`PAID_STATUS_LABELS` removed from `app/reports/service.py`; the account view, paid-students report, and student search rows all classify through `classify_paid_status`. The tone maps that used to live in `reports/routes.py` and `students/routes.py` (two copies of the same dict) now come from the module and are passed to templates as `charge_status_labels`/`charge_status_tones`; the account-finance template renders from the same shared maps via the `badge` macro instead of the hardcoded `charge_status_badge` macro (deleted). Route files define no statuses or tones.

Verification:
- Full suite green (655 tests), `mypy app` clean on 51 source files.
- New `tests/test_charge_status.py` is the one place the classifier is tested: status string constants, paid/partial/unpaid classification (incl. overpayment floored at zero), and label/tone coverage. Existing payment/report service and route tests are unchanged apart from importing `ChargeStatus` from the shared module, and stay green.

Commit: 52389fe
