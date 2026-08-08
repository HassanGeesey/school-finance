"""Charge status: one enum, one classifier, one tone map.

"paid / partial / unpaid" is a single concept owned here. The student account,
the reports, and the student lists all read the status and its rendering
(label + tone) from this module instead of each re-deriving them. Amounts are
integer cents (``app.money``) throughout.
"""

from __future__ import annotations

from .money import Money


class ChargeStatus:
    PAID = "paid"
    PARTIAL = "partial"
    UNPAID = "unpaid"


CHARGE_STATUS_LABELS = {
    ChargeStatus.PAID: "Paid",
    ChargeStatus.PARTIAL: "Partial",
    ChargeStatus.UNPAID: "Unpaid",
}

CHARGE_STATUS_TONES = {
    ChargeStatus.PAID: "success",
    ChargeStatus.PARTIAL: "warning",
    ChargeStatus.UNPAID: "error",
}


def classify_paid_status(net_cents: Money, paid_cents: Money) -> tuple[str, Money]:
    """The paid status and remaining cents for a charge net vs paid.

    A charge is ``paid`` when nothing is left after payments, ``partial`` when
    some but not all has been paid, else ``unpaid``. ``remaining_cents`` is the
    live amount still owed, floored at zero (overpayment never goes negative).
    """
    remaining = max(net_cents - paid_cents, 0)
    if remaining <= 0:
        return ChargeStatus.PAID, remaining
    if paid_cents > 0:
        return ChargeStatus.PARTIAL, remaining
    return ChargeStatus.UNPAID, remaining
