"""The one accessor every platform reads, and the only writer of stored state.

STORED STATE IS SEPARATE FROM DERIVED STATE. When a chore was done is
asserted by a person and must survive a restart, so it lives in a `Store`,
keyed on the chore's SUBENTRY id -- never its name, which a person can
rename. Everything else (overdue, due today, days until) is computed from
that plus the clock and is never persisted: a stored derived value is one
that can be stale and right-looking at the same time.

WHY A COORDINATOR when nothing here does I/O: every answer turns over at
midnight with no state change to trigger it, so something has to
re-evaluate on a timer or a wall panel spends the morning saying a chore is
due tomorrow. Five minutes is a rollover-latency budget, not a poll.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .chores import ChoreState, push_history, rank, resolve
from .const import (
    CONF_AREA,
    CONF_INTERVAL,
    CONF_NAME,
    CONF_SOON_DAYS,
    DEFAULT_INTERVAL,
    DEFAULT_SOON_DAYS,
    DOMAIN,
    DUE_STATUSES,
    HISTORY_LIMIT,
    STATUS_NEVER,
    STATUS_OVERDUE,
    STATUS_SOON,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
UPDATE_INTERVAL = timedelta(minutes=5)

type HouseCleaningConfigEntry = ConfigEntry[HouseCleaningCoordinator]


class HouseCleaningCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reduces stored completions plus the calendar into what every platform
    renders."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)
        self.entry = entry
        self.entry_id = entry.entry_id
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._state: dict[str, Any] = {}

    # -- stored state ------------------------------------------------------

    async def async_load(self) -> None:
        self._state = await self._store.async_load() or {}
        self._state.setdefault("chores", {})

    async def _async_persist(self) -> None:
        await self._store.async_save(self._state)
        # Immediate, not debounced: the surface is a wall panel where somebody
        # walks the house tapping chores in a row, and the coordinator's own
        # 10s debounce made every tap after the first read as ignored
        # (waste_collection measured it). The update is pure arithmetic.
        await self.async_refresh()

    def _chore_state(self, subentry_id: str) -> dict[str, Any]:
        return self._state["chores"].setdefault(subentry_id, {})

    # -- the writes the platforms and services make ------------------------

    async def async_mark_done(self, subentry_id: str, done: date | None = None) -> None:
        """Stamp a completion. `done` is a DATE when backfilled ("I did it
        yesterday"); the stored value is still an instant so the history
        keeps its order, at midday local so it renders on the right day for
        any viewer an hour off."""
        if done is None or done == dt_util.now().date():
            stamp = dt_util.utcnow()
        else:
            stamp = dt_util.as_utc(dt_util.start_of_local_day(done).replace(hour=12))
        row = self._chore_state(subentry_id)
        row["history"] = push_history(row.get("history", []), stamp.isoformat(), HISTORY_LIMIT)
        # `done` is the LATEST completion, which is not necessarily the one
        # just written: a backfill for last week must not move a chore done
        # yesterday back a week.
        row["done"] = max(row["history"])
        await self._async_persist()

    async def async_undo(self, subentry_id: str) -> bool:
        """Drop the most recent completion -- a mis-tap on a wall. Returns
        False when there was nothing to undo, so the service can say so."""
        row = self._chore_state(subentry_id)
        history: list[str] = row.get("history", [])
        if not history:
            return False
        # The newest is the max, not [0]: a backfill can be pushed after a
        # later completion.
        history.remove(max(history))
        row["history"] = history
        row["done"] = max(history) if history else None
        await self._async_persist()
        return True

    async def async_prune(self) -> None:
        """Drop completions for chores whose subentry is gone, so the store
        does not grow rows nothing reads. Called at setup, after the
        subentry removal that orphaned them has already reloaded the entry."""
        stale = [sid for sid in self._state["chores"] if sid not in self.entry.subentries]
        for sid in stale:
            del self._state["chores"][sid]
        if stale:
            await self._store.async_save(self._state)

    # -- the reduction -----------------------------------------------------

    @property
    def soon_days(self) -> int:
        return int((self.entry.options or {}).get(CONF_SOON_DAYS, DEFAULT_SOON_DAYS))

    async def _async_update_data(self) -> dict[str, Any]:
        """Never raises. The inputs are this entry's own subentries, its own
        store and the clock, so an exception could only be a bug in the
        arithmetic, and taking every entity unavailable is the worst way to
        report one."""
        today = dt_util.now().date()
        soon = self.soon_days
        chores: dict[str, dict[str, Any]] = {}
        for sid, sub in self.entry.subentries.items():
            stored = self._state["chores"].get(sid, {})
            done_at = self.as_datetime(stored.get("done"))
            interval = int(sub.data.get(CONF_INTERVAL, DEFAULT_INTERVAL))
            state = resolve(
                dt_util.as_local(done_at).date() if done_at else None, interval, today, soon
            )
            chores[sid] = {
                "subentry_id": sid,
                "name": sub.data.get(CONF_NAME, sub.title),
                "area": sub.data.get(CONF_AREA),
                "interval_days": interval,
                "state": state,
                "done_at": done_at,
                "history": list(stored.get("history", [])),
            }
        return {"today": today, "soon_days": soon, "chores": chores}

    # -- convenience for the roll-up ---------------------------------------

    def rows(self) -> list[dict[str, Any]]:
        """Every chore, most urgent first."""
        rows = list((self.data or {}).get("chores", {}).values())
        rows.sort(key=lambda r: (rank(r["state"]), r["name"].lower()))
        return rows

    def rollup(self) -> dict[str, Any]:
        rows = self.rows()

        def names(pred) -> list[str]:
            return [r["name"] for r in rows if pred(r["state"])]

        by_room: dict[str, dict[str, int]] = {}
        for r in rows:
            key = r["area"] or ""
            bucket = by_room.setdefault(key, {"total": 0, "due": 0, "never": 0})
            bucket["total"] += 1
            if r["state"].status in DUE_STATUSES:
                bucket["due"] += 1
            if r["state"].status == STATUS_NEVER:
                bucket["never"] += 1

        dated = [r for r in rows if r["state"].due is not None]
        dated.sort(key=lambda r: (r["state"].days_until, r["name"].lower()))
        nxt = dated[0] if dated else None

        return {
            "due_count": sum(1 for r in rows if r["state"].status in DUE_STATUSES),
            "overdue_items": names(lambda s: s.status == STATUS_OVERDUE),
            "due_items": names(lambda s: s.status in DUE_STATUSES),
            "soon_items": names(lambda s: s.status == STATUS_SOON),
            "never_items": names(lambda s: s.status == STATUS_NEVER),
            "by_room": by_room,
            "rows": [self.row_attributes(r) for r in rows],
            "next": nxt,
        }

    @staticmethod
    def row_attributes(row: dict[str, Any]) -> dict[str, Any]:
        s: ChoreState = row["state"]
        return {
            "name": row["name"],
            "area": row["area"],
            "interval_days": row["interval_days"],
            "status": s.status,
            "due": s.due.isoformat() if s.due else None,
            "days_until": s.days_until,
            "days_since": s.days_since,
            "last_done": row["done_at"].isoformat() if row["done_at"] else None,
        }

    @staticmethod
    def as_datetime(value) -> datetime | None:
        return dt_util.parse_datetime(value) if value else None

