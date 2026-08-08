"""One payment-allocation planner.

The clearing rule — a payment applies to the oldest unpaid charges first,
each charge is reduced until settled before the next is touched, and any
excess becomes a credit — lives here in exactly one callable. Recording,
previewing, and the paid-cents grouping that reports and arrears need all
flow through it, so changing the rule changes one function.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..fees.service import net_cents
from ..models import Charge, PaymentAllocation


def paid_cents_by_charge(
    session: Session, charge_ids: Iterable[int] | None = None
) -> dict[int, int]:
    """Total amount already cleared per charge, across every payment.

    When ``charge_ids`` is given, only those charges are summed (already
    settled and unpaid alike); otherwise every allocation counts.
    """
    if charge_ids is not None:
        ids = list(charge_ids)
        if not ids:
            return {}
    else:
        ids = None
    query = session.query(
        PaymentAllocation.charge_id, func.sum(PaymentAllocation.amount_cents)
    )
    if ids is not None:
        query = query.filter(PaymentAllocation.charge_id.in_(ids))
    rows = query.group_by(PaymentAllocation.charge_id).all()
    return {charge_id: int(total) for charge_id, total in rows}


def plan_application(
    charges: Iterable[Charge],
    paid_cents: dict[int, int],
    amount_cents: int,
) -> tuple[dict[int, int], int]:
    """Allocate ``amount_cents`` across ``charges``, oldest period first.

    ``charges`` must already be ordered oldest first (year, month, id). Each
    charge is reduced until settled before the next is touched; already settled
    charges are skipped. Returns ``(applied_by_charge, credit_cents)`` where
    ``applied_by_charge`` maps charge id to the amount applied and
    ``credit_cents`` is whatever remains after every charge is settled — an
    overpayment becomes a credit on the account.
    """
    remaining = amount_cents
    applied: dict[int, int] = {}
    for charge in charges:
        if remaining <= 0:
            break
        unpaid = max(
            net_cents(charge, list(charge.adjustments))
            - paid_cents.get(charge.id, 0),
            0,
        )
        if unpaid <= 0:
            continue
        applied[charge.id] = min(unpaid, remaining)
        remaining -= applied[charge.id]
    return applied, remaining
