"""The rule, exercised with Home Assistant absent."""

from datetime import date, datetime

import pytest
from house_cleaning.chores import (
    ChoreValueError,
    parse_done_at,
    push_history,
    rank,
    resolve,
    validate_interval,
    validate_soon_days,
)
from house_cleaning.const import (
    STATUS_DUE,
    STATUS_NEVER,
    STATUS_OK,
    STATUS_OVERDUE,
    STATUS_SOON,
)

TODAY = date(2026, 9, 12)


# -- resolve -----------------------------------------------------------------


def test_never_done_is_its_own_state_not_overdue():
    s = resolve(None, 7, TODAY, 2)
    assert s.status == STATUS_NEVER
    assert s.due is None and s.days_until is None and s.days_since is None


def test_due_today():
    s = resolve(date(2026, 9, 5), 7, TODAY, 2)
    assert s.status == STATUS_DUE
    assert s.due == TODAY and s.days_until == 0 and s.days_since == 7


def test_overdue_carries_negative_days():
    s = resolve(date(2026, 9, 1), 7, TODAY, 2)
    assert s.status == STATUS_OVERDUE
    assert s.days_until == -4 and s.days_since == 11


@pytest.mark.parametrize("last, expected", [(date(2026, 9, 7), STATUS_SOON), (date(2026, 9, 6), STATUS_SOON), (date(2026, 9, 8), STATUS_OK)])
def test_soon_window_is_inclusive_of_its_edge(last, expected):
    # interval 7, soon 2: due 9/13 (1 day) soon, 9/14 (2 days) soon, 9/15 (3) ok
    assert resolve(last, 7, TODAY, 2).status == expected


def test_soon_window_of_zero_is_off():
    assert resolve(date(2026, 9, 6), 7, TODAY, 0).status == STATUS_OK


def test_done_today_is_ok_for_the_whole_interval():
    s = resolve(TODAY, 1, TODAY, 2)
    assert s.status == STATUS_SOON  # due tomorrow, inside a 2-day window
    assert resolve(TODAY, 30, TODAY, 2).status == STATUS_OK


# -- rank --------------------------------------------------------------------


def test_rank_orders_overdue_before_due_before_soon_before_never_before_ok():
    states = [
        resolve(TODAY, 30, TODAY, 2),  # ok
        resolve(None, 7, TODAY, 2),  # never
        resolve(date(2026, 9, 7), 7, TODAY, 2),  # soon
        resolve(date(2026, 9, 5), 7, TODAY, 2),  # due
        resolve(date(2026, 9, 1), 7, TODAY, 2),  # overdue
    ]
    ordered = sorted(states, key=rank)
    assert [s.status for s in ordered] == [STATUS_OVERDUE, STATUS_DUE, STATUS_SOON, STATUS_NEVER, STATUS_OK]


def test_rank_puts_the_most_overdue_first():
    a = resolve(date(2026, 9, 1), 7, TODAY, 2)  # -4
    b = resolve(date(2026, 8, 20), 7, TODAY, 2)  # -16
    assert sorted([a, b], key=rank)[0] is b


# -- validate_interval / validate_soon_days -----------------------------------


@pytest.mark.parametrize("value, expected", [(7, 7), (7.0, 7), ("7", 7), (1, 1), (365, 365)])
def test_interval_accepts_whole_days_in_any_spelling(value, expected):
    assert validate_interval(value) == expected


@pytest.mark.parametrize("value", [0, 366, -1, 7.5, "week", None, True, ""])
def test_interval_refuses_and_names_the_field(value):
    with pytest.raises(ChoreValueError) as err:
        validate_interval(value)
    assert err.value.field == "interval_days"
    assert err.value.value == value


@pytest.mark.parametrize("value, expected", [(0, 0), (14, 14), ("3", 3)])
def test_soon_days_accepts(value, expected):
    assert validate_soon_days(value) == expected


@pytest.mark.parametrize("value", [15, -1, 1.5, "soon", False])
def test_soon_days_refuses(value):
    with pytest.raises(ChoreValueError):
        validate_soon_days(value)


# -- parse_done_at -------------------------------------------------------------


def test_done_at_none_is_today():
    assert parse_done_at(None, TODAY) == TODAY


@pytest.mark.parametrize(
    "value", ["2026-09-11", "2026-09-11T08:00:00+00:00", date(2026, 9, 11), datetime(2026, 9, 11, 8)]
)
def test_done_at_takes_a_date_in_any_form(value):
    assert parse_done_at(value, TODAY) == date(2026, 9, 11)


def test_done_at_refuses_the_future():
    with pytest.raises(ChoreValueError) as err:
        parse_done_at("2026-09-13", TODAY)
    assert err.value.field == "done_at"


@pytest.mark.parametrize("value", ["yesterday", "2026-13-01", 42, ""])
def test_done_at_refuses_nonsense(value):
    with pytest.raises(ChoreValueError):
        parse_done_at(value, TODAY)


# -- push_history ------------------------------------------------------------


def test_history_is_newest_first_and_bounded():
    h = push_history(["b", "a"], "c", 3)
    assert h == ["c", "b", "a"]
    assert push_history(h, "d", 3) == ["d", "c", "b"]


# -- the self-test LAW §4 asks for: prove the assertions CAN fail --------------


def test_the_suite_can_fail():
    assert resolve(date(2026, 9, 1), 7, TODAY, 2).status != STATUS_OK
