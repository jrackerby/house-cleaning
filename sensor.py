"""Last done and next due per chore; the due count and next chore for the house."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_NAME
from .coordinator import HouseCleaningConfigEntry
from .entity import ChoreEntity, HouseEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HouseCleaningConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([DueCountSensor(coordinator), NextChoreSensor(coordinator)])

    # Chore entities are added AGAINST THEIR SUBENTRY, so Home Assistant files
    # each device under the subentry that created it and removing that
    # subentry takes its entities with it.
    for sid, sub in entry.subentries.items():
        name = sub.data.get(CONF_NAME, sub.title)
        async_add_entities(
            [LastDoneSensor(coordinator, sid, name), NextDueSensor(coordinator, sid, name)],
            config_subentry_id=sid,
        )


def _midday_local(day: date | None):
    """A DATE rendered as a timestamp. Midday local, not midnight: a
    timestamp renders as an instant, and midnight lands on the wrong side
    of the day for any viewer an hour off. The `date` attribute carries the
    plain date for anything that needs it exactly."""
    if day is None:
        return None
    return dt_util.start_of_local_day(day).replace(hour=12)


class LastDoneSensor(ChoreEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_done"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "last_done")

    @property
    def native_value(self):
        return self.row.get("done_at")

    @property
    def extra_state_attributes(self) -> dict:
        row = self.row
        return {
            "area": row.get("area"),
            "interval_days": row.get("interval_days"),
            "history": row.get("history", []),
            "done_count": len(row.get("history", [])),
        }


class NextDueSensor(ChoreEntity, SensorEntity):
    """`unknown` with `status: never` while nothing has been recorded --
    never `unavailable`, which reads as broken."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_due"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "next_due")

    @property
    def native_value(self):
        state = self.row.get("state")
        return _midday_local(state.due) if state else None

    @property
    def extra_state_attributes(self) -> dict:
        row = self.row
        state = row.get("state")
        return {
            "area": row.get("area"),
            "interval_days": row.get("interval_days"),
            "status": state.status if state else None,
            "date": state.due.isoformat() if state and state.due else None,
            "days_until": state.days_until if state else None,
            "days_since": state.days_since if state else None,
        }


class DueCountSensor(HouseEntity, SensorEntity):
    """How many chores are due today or overdue. Never-done chores are NOT
    in the count -- they are named in `never_items` instead, so a fresh
    install reads as unrecorded rather than as behind."""

    _attr_translation_key = "due_count"
    _attr_native_unit_of_measurement = "chores"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "due_count")

    @property
    def native_value(self) -> int:
        return self.coordinator.rollup()["due_count"]

    @property
    def extra_state_attributes(self) -> dict:
        r = self.coordinator.rollup()
        return {
            "overdue_items": r["overdue_items"],
            "due_items": r["due_items"],
            "soon_items": r["soon_items"],
            "never_items": r["never_items"],
            "by_room": r["by_room"],
            "rows": r["rows"],
            "soon_days": self.coordinator.data.get("soon_days"),
        }


class NextChoreSensor(HouseEntity, SensorEntity):
    """The chore due soonest -- already overdue counts as soonest. `unknown`
    when no chore has ever been recorded."""

    _attr_translation_key = "next_chore"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "next_chore")

    @property
    def native_value(self):
        nxt = self.coordinator.rollup()["next"]
        return nxt["name"] if nxt else None

    @property
    def extra_state_attributes(self) -> dict:
        nxt = self.coordinator.rollup()["next"]
        if not nxt:
            return {"status": None, "due": None, "days_until": None, "area": None}
        s = nxt["state"]
        return {
            "status": s.status,
            "due": s.due.isoformat() if s.due else None,
            "days_until": s.days_until,
            "area": nxt["area"],
        }
