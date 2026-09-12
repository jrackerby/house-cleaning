"""The rule: where a chore stands against its cadence, and what a caller may
write about it.

IMPORTS NOTHING FROM `homeassistant`, deliberately. Every answer a surface or
an automation reads -- overdue, due today, due soon, never done -- comes from
here, so this is the half of the integration the suite can exercise with
core absent (tests/conftest.py stages this module and const.py alone).
The platforms only render what this returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .const import (
    MAX_INTERVAL,
    MAX_SOON_DAYS,
    MIN_INTERVAL,
    MIN_SOON_DAYS,
    STATUS_DUE,
    STATUS_NEVER,
    STATUS_OK,
    STATUS_OVERDUE,
    STATUS_SOON,
)


class ChoreValueError(ValueError):
    """A value the integration will not store. Carries the field and the
    value so the caller can name both -- a refusal that does not say what it
    refused is indistinguishable from a bug."""

    def __init__(self, field: str, value: object) -> None:
        super().__init__(f"{field}: {value!r}")
        self.field = field
        self.value = value


@dataclass(frozen=True)
class ChoreState:
    """One chore, resolved against today."""

    status: str
    last_done: date | None
    due: date | None
    # Negative once overdue, zero on the day, None when never done.
    days_until: int | None
    days_since: int | None


def validate_interval(value: object) -> int:
    """A cadence in whole days, or a refusal.

    Accepts an int, or a float/str that IS a whole number -- a number
    selector hands back 7.0 for 7 and a service call may carry "7". Anything
    fractional, non-numeric, or outside the bounds is refused rather than
    rounded, because a rounded cadence is one nobody chose.
    """
    if isinstance(value, bool):
        raise ChoreValueError("interval_days", value)
    try:
        as_float = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise ChoreValueError("interval_days", value) from err
    if not as_float.is_integer():
        raise ChoreValueError("interval_days", value)
    days = int(as_float)
    if days < MIN_INTERVAL or days > MAX_INTERVAL:
        raise ChoreValueError("interval_days", value)
    return days


def validate_soon_days(value: object) -> int:
    if isinstance(value, bool):
        raise ChoreValueError("soon_days", value)
    try:
        as_float = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise ChoreValueError("soon_days", value) from err
    if not as_float.is_integer():
        raise ChoreValueError("soon_days", value)
    days = int(as_float)
    if days < MIN_SOON_DAYS or days > MAX_SOON_DAYS:
        raise ChoreValueError("soon_days", value)
    return days


def parse_done_at(value: object, today: date) -> date:
    """When a chore was done, as a date, from what a caller sent.

    `None` means now. A date or datetime (an object, or ISO text) is taken
    as given. A date in the FUTURE is refused: "I will do it tomorrow" is a
    plan, and stamping it as done would silently mark the chore complete
    before anyone touched it.
    """
    if value is None:
        return today
    if isinstance(value, datetime):
        done = value.date()
    elif isinstance(value, date):
        done = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            done = date.fromisoformat(text[:10]) if len(text) >= 10 else date.fromisoformat(text)
        except ValueError as err:
            raise ChoreValueError("done_at", value) from err
    else:
        raise ChoreValueError("done_at", value)
    if done > today:
        raise ChoreValueError("done_at", value)
    return done


def resolve(
    last_done: date | None, interval_days: int, today: date, soon_days: int
) -> ChoreState:
    """Where one chore stands today.

    `soon_days` is the window ahead of the due date in which a chore is
    called SOON: with 2, a chore due the day after tomorrow is soon, one due
    in three days is ok. Zero disables the window. `days_until` is the raw
    figure either way, so a surface that wants its own threshold has it.
    """
    if last_done is None:
        return ChoreState(STATUS_NEVER, None, None, None, None)

    due = last_done + timedelta(days=interval_days)
    days_until = (due - today).days
    days_since = (today - last_done).days

    if days_until < 0:
        status = STATUS_OVERDUE
    elif days_until == 0:
        status = STATUS_DUE
    elif days_until <= soon_days:
        status = STATUS_SOON
    else:
        status = STATUS_OK
    return ChoreState(status, last_done, due, days_until, days_since)


# Sort weight per status: most urgent first. NEVER sits after DUE rather
# than first -- it needs a first record, not a rescue, and putting nine
# never-done starter chores ahead of the one thing actually overdue would
# bury the real answer under the empty ones.
_STATUS_RANK = {
    STATUS_OVERDUE: 0,
    STATUS_DUE: 1,
    STATUS_SOON: 2,
    STATUS_NEVER: 3,
    STATUS_OK: 4,
}


def rank(state: ChoreState) -> tuple[int, int]:
    """A sort key: urgency, then how far along -- an overdue chore that is
    ten days late outranks one that is a day late."""
    days = state.days_until if state.days_until is not None else 0
    return (_STATUS_RANK.get(state.status, 9), days)


def push_history(history: list[str], stamp: str, limit: int) -> list[str]:
    """A completion prepended to a bounded, newest-first list."""
    return [stamp, *history][:limit]
