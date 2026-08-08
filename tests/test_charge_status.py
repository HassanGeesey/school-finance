"""Charge status: the single paid/partial/unpaid enum, classifier, and tones.

The status concept lives in exactly one module (``app.charge_status``) so the
account, reports, and lists read the same classifier and the same rendering —
this is the one place the classifier is tested.
"""

from app.charge_status import (
    CHARGE_STATUS_LABELS,
    CHARGE_STATUS_TONES,
    ChargeStatus,
    classify_paid_status,
)


def test_status_values_are_the_canonical_strings():
    assert ChargeStatus.PAID == "paid"
    assert ChargeStatus.PARTIAL == "partial"
    assert ChargeStatus.UNPAID == "unpaid"


def test_classify_paid_when_nothing_remains():
    assert classify_paid_status(10000, 10000) == (ChargeStatus.PAID, 0)


def test_classify_paid_floors_remaining_at_zero_when_overpaid():
    assert classify_paid_status(10000, 15000) == (ChargeStatus.PAID, 0)


def test_classify_partial_when_some_but_not_all_paid():
    assert classify_paid_status(10000, 4000) == (ChargeStatus.PARTIAL, 6000)


def test_classify_unpaid_when_nothing_paid():
    assert classify_paid_status(10000, 0) == (ChargeStatus.UNPAID, 10000)


def test_classify_unpaid_keeps_net_when_no_payment():
    assert classify_paid_status(5000, 0) == (ChargeStatus.UNPAID, 5000)


def test_labels_and_tones_cover_exactly_the_three_statuses():
    assert set(CHARGE_STATUS_LABELS) == {ChargeStatus.PAID, ChargeStatus.PARTIAL, ChargeStatus.UNPAID}
    assert set(CHARGE_STATUS_TONES) == set(CHARGE_STATUS_LABELS)
    assert None not in CHARGE_STATUS_TONES.values()


def test_classify_returns_values_that_are_renderable():
    for net, paid in [(0, 0), (1, 1), (1, 0), (1, 2)]:
        status, remaining = classify_paid_status(net, paid)
        assert CHARGE_STATUS_LABELS[status]
        assert CHARGE_STATUS_TONES[status]
        assert remaining >= 0
