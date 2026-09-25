"""
Turns extracted contract fields into an actionable risk level and
a human-readable "why" explanation.

Risk is driven by the CANCELLATION DEADLINE (end_date - notice_period_days),
i.e. the last day you can act to stop an unwanted auto-renewal - not the
renewal date itself. That deadline is the thing that actually matters.
"""

from datetime import date, datetime
from models import Contract


def days_until(iso_date: str) -> int:
    d = datetime.fromisoformat(iso_date).date()
    return (d - date.today()).days


def assess_risk(c: Contract):
    """Returns (risk_level: str, days_left: int|None, reason: str)."""

    if c.auto_renews is False:
        return "LOW", None, "Contract does not auto-renew — no action required unless you plan to renegotiate."

    deadline = c.cancellation_deadline or c.end_date
    if not deadline:
        return "UNKNOWN", None, "No renewal or end date could be found — review the contract manually."

    try:
        d_left = days_until(deadline)
    except Exception:
        return "UNKNOWN", None, "Date found could not be parsed — review manually."

    if d_left < 0:
        return "PAST", d_left, f"Deadline ({deadline}) has already passed — the contract may have already auto-renewed."
    if d_left <= 7:
        level = "CRITICAL"
    elif d_left <= 30:
        level = "HIGH"
    elif d_left <= 60:
        level = "MEDIUM"
    else:
        level = "LOW"

    if c.cancellation_deadline:
        reason = f"Cancellation window closes {c.cancellation_deadline} ({d_left} days) — after that it auto-renews."
    else:
        reason = f"Contract end/renewal date is {c.end_date} ({d_left} days) — no explicit notice period was found, treat this date as the deadline."

    return level, d_left, reason


RISK_ORDER = {"PAST": 0, "CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4, "UNKNOWN": 5}


def sort_key(c: Contract):
    level, days_left, _ = assess_risk(c)
    order = RISK_ORDER.get(level, 5)
    # within same level, soonest deadline first; unknown/past push to edges sensibly
    day_val = days_left if days_left is not None else 99999
    return (order, day_val)
