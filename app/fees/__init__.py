"""Fee billing feature (derived model): templates, waivers, closed months, and the account seam.

Covers the Admin's fee-template management (:mod:`app.fees.service`), the
per-(student, month) waiver surface, the school-wide closed-month list, and the
derived per-student account comparison (:mod:`app.fees.account`) that replaces
the old charge-row generation.
"""
